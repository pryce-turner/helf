import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { workoutsApi } from "@/lib/api";
import { derivedActuals } from "@/lib/setTiles";
import {
    buildPlayerPhases,
    type PlayerPhase,
    type PlayerTile,
} from "@/lib/workoutPlayer";

/**
 * The day player: executes the day's incomplete set tiles in order, and
 * records what was actually performed (plan 0018).
 *
 * Timing is the interval timer's: absolute deadlines, never a decremented
 * counter. Each timed phase stores `endAt = performance.now() + duration`
 * and a rAF loop reads the remainder; a busy frame shows up once as overshoot
 * carried into the next deadline. Pause banks the remainder — paused wall
 * time reaches no actual field.
 *
 * Writes happen **before** advancement and from the immutable snapshot taken
 * at Play: a tile's performance is saved, then the run moves on; a failed
 * save halts the run with Retry, so the UI never claims unsaved work reached
 * the log, and a tile edited mid-run is still written as it was at Play.
 */

export type PlayerStatus =
    | "idle"
    | "running"
    | "paused"
    | "saving"
    | "error"
    | "done";

/**
 * The totals a naturally completed tile records, from the snapshot: the
 * shared `derivedActuals` rule (the same one the server's `_derive_actuals`
 * follows), with absent fields omitted so the API never sees them.
 */
const snapshotTotals = (tile: PlayerTile) =>
    Object.fromEntries(
        Object.entries(derivedActuals(tile)).filter(([, value]) => value != null),
    );

interface BeepSpec {
    frequency: number;
    durationMs: number;
    delayMs?: number;
    type?: OscillatorType;
    gain?: number;
}

const PIP_BEFORE_WORK: BeepSpec[] = [{ frequency: 988, durationMs: 70, gain: 0.25 }];
const PIP_BEFORE_REST: BeepSpec[] = [{ frequency: 698, durationMs: 70, gain: 0.25 }];

const COUNTDOWN_PIP: Partial<Record<PlayerPhase["kind"], BeepSpec[]>> = {
    getReady: PIP_BEFORE_WORK,
    work: PIP_BEFORE_REST,
    rest: PIP_BEFORE_WORK,
    restAfter: PIP_BEFORE_WORK,
};

const WORK_START: BeepSpec[] = [
    { frequency: 1319, durationMs: 450, type: "triangle", gain: 0.5 },
    { frequency: 659, durationMs: 450, gain: 0.3 },
];

const REST_START: BeepSpec[] = [
    { frequency: 784, durationMs: 160, gain: 0.35 },
    { frequency: 587, durationMs: 280, delayMs: 180, gain: 0.35 },
];

const SESSION_DONE: BeepSpec[] = [
    { frequency: 880, durationMs: 120, gain: 0.4 },
    { frequency: 1108, durationMs: 120, delayMs: 150, gain: 0.4 },
    { frequency: 1318, durationMs: 120, delayMs: 300, gain: 0.4 },
    { frequency: 1760, durationMs: 600, delayMs: 450, gain: 0.45 },
];

const playBeeps = (ctx: AudioContext, specs: BeepSpec[]) => {
    if (ctx.state === "suspended") void ctx.resume();
    for (const {
        frequency,
        durationMs,
        delayMs = 0,
        type = "sine",
        gain: peak = 0.3,
    } of specs) {
        const start = ctx.currentTime + delayMs / 1000;
        const end = start + durationMs / 1000;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = type;
        osc.frequency.value = frequency;
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(peak, start + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, end);
        osc.connect(gain).connect(ctx.destination);
        osc.start(start);
        osc.stop(end + 0.05);
    }
};

/** What a failed write remembers, so Retry repeats it byte for byte. */
interface FailedOp {
    write: () => Promise<unknown>;
    afterwards: () => void;
}

export function useWorkoutPlayer(incomplete: PlayerTile[] = []) {
    const queryClient = useQueryClient();

    const [status, setStatus] = useState<PlayerStatus>("idle");
    const [tiles, setTiles] = useState<PlayerTile[]>([]);
    const [phases, setPhases] = useState<PlayerPhase[]>([]);
    const [phaseIndex, setPhaseIndex] = useState(0);
    const [remainingMs, setRemainingMs] = useState(0);
    const [failedOp, setFailedOp] = useState<FailedOp | null>(null);

    const endAtRef = useRef(0);
    // Wall-clock start of the current phase. The countdown's deadline gets
    // overshoot carried into it; measurement must not — a skip or a stop
    // records the time the phase actually ran, not the carried frames.
    const phaseStartAtRef = useRef(0);
    const rafRef = useRef(0);
    const audioRef = useRef<AudioContext | null>(null);
    const lastTickSecondRef = useRef(-1);
    // Anything written this run: a Stop that wrote shows "done", one that
    // wrote nothing simply resets — a run abandoned before any work is not
    // a result.
    const wroteAnythingRef = useRef(false);

    // The current tile's measured performance, banked phase by phase. A work
    // rep banks when it *ends* — full at a natural boundary, partial on a
    // skip — and counts in `bankedReps` only when it ran out naturally (a
    // skipped rep is a partial rep: its seconds count, the rep does not —
    // the same rule as a Stop). `skippedWork` is what marks the tile
    // `ended_early` at the write. Reset per tile at its save.
    const bankedWorkMsRef = useRef(0);
    const bankedRestMsRef = useRef(0);
    const bankedRepsRef = useRef(0);
    const skippedWorkRef = useRef(false);

    const resetBanks = useCallback(() => {
        bankedWorkMsRef.current = 0;
        bankedRestMsRef.current = 0;
        bankedRepsRef.current = 0;
        skippedWorkRef.current = false;
    }, []);

    const phase = phases[phaseIndex] ?? null;
    const activeTileId =
        phase && tiles[phase.tileIndex] ? tiles[phase.tileIndex].doc_id : null;

    const invalidatePerformance = useCallback(() => {
        for (const key of ["workouts", "calendar", "exercises", "progression", "mobility"]) {
            void queryClient.invalidateQueries({ queryKey: [key] });
        }
    }, [queryClient]);

    /** Create/resume the context. Must be called from a user gesture. */
    const ensureAudio = (): AudioContext | null => {
        const Ctor =
            window.AudioContext ??
            (window as unknown as { webkitAudioContext?: typeof AudioContext })
                .webkitAudioContext;
        if (!Ctor) return null;
        if (!audioRef.current) audioRef.current = new Ctor();
        if (audioRef.current.state === "suspended") void audioRef.current.resume();
        return audioRef.current;
    };

    /** The run is over, completed or stopped with writes behind it. */
    const finish = useCallback(() => {
        setStatus("done");
        if (audioRef.current) playBeeps(audioRef.current, SESSION_DONE);
    }, []);

    /**
     * One write, then the continuation. The schedule freezes while it is in
     * flight (`saving` pauses the countdown loop), so a tile is never skipped
     * unsaved and never written twice; on failure the run halts with the op
     * held for Retry.
     */
    const saveThen = useCallback(
        (write: () => Promise<unknown>, afterwards: () => void) => {
            setStatus("saving");
            write()
                .then(() => {
                    wroteAnythingRef.current = true;
                    invalidatePerformance();
                    afterwards();
                })
                .catch(() => {
                    setFailedOp({ write, afterwards });
                    setStatus("error");
                });
        },
        [invalidatePerformance],
    );

    /** The measured totals from the banks, for a timed tile. */
    const bankedTotals = useCallback(
        (tile: PlayerTile, extraWorkMs = 0, extraRestMs = 0) => ({
            ended_early: skippedWorkRef.current,
            ...(tile.reps != null ? { completed_reps: bankedRepsRef.current } : {}),
            ...(tile.work_seconds != null
                ? {
                      actual_work_seconds:
                          Math.round(((bankedWorkMsRef.current + extraWorkMs) / 1000) * 10) / 10,
                  }
                : {}),
            ...(tile.rest_seconds != null
                ? {
                      actual_rest_seconds:
                          Math.round(((bankedRestMsRef.current + extraRestMs) / 1000) * 10) / 10,
                  }
                : {}),
        }),
        [],
    );

    const saveTile = useCallback(
        (tileIndex: number, afterwards: () => void) => {
            const tile = tiles[tileIndex];
            // An untimed tile has nothing measured: the shared derived rule.
            // A timed one writes what was banked, skip or no skip.
            const payload =
                tile.work_seconds == null
                    ? snapshotTotals(tile)
                    : bankedTotals(tile);
            saveThen(
                () => workoutsApi.perform(tile.doc_id, payload),
                () => {
                    resetBanks();
                    afterwards();
                },
            );
        },
        [tiles, saveThen, bankedTotals, resetBanks],
    );

    /**
     * The one way past a phase, shared by the countdown's natural boundary
     * and by Skip: the finished phase banks (full at a boundary, partial on
     * skip), the boundary saves fire before advancing, and the next phase
     * gets a fresh deadline with any overshoot carried.
     */
    const advancePast = useCallback(
        (
            prevPhase: PlayerPhase,
            prevIndex: number,
            phaseMs: number,
            overshootMs: number,
            skipped: boolean,
        ) => {
            if (prevPhase.kind === "work") {
                bankedWorkMsRef.current += phaseMs;
                if (skipped) skippedWorkRef.current = true;
                else bankedRepsRef.current += 1;
            } else if (prevPhase.kind === "rest") {
                bankedRestMsRef.current += phaseMs;
            }

            const nextIndex = prevIndex + 1;
            const advance = () => {
                if (nextIndex >= phases.length) {
                    setRemainingMs(0);
                    finish();
                    return;
                }
                const next = phases[nextIndex];
                phaseStartAtRef.current = performance.now();
                endAtRef.current =
                    phaseStartAtRef.current + next.durationMs - overshootMs;
                lastTickSecondRef.current = -1;
                setPhaseIndex(nextIndex);
                setRemainingMs(next.durationMs - overshootMs);
                setStatus("running");
                if (audioRef.current) {
                    playBeeps(
                        audioRef.current,
                        next.kind === "work" ? WORK_START : REST_START,
                    );
                }
            };

            // A tile's performance writes when its last work rep ends; the
            // divider's when the rest-after runs out (or is cut short).
            const tileFinished =
                prevPhase.kind === "work" && prevPhase.rep === prevPhase.repsTotal;
            if (tileFinished) {
                saveTile(prevPhase.tileIndex, advance);
            } else if (prevPhase.kind === "restAfter") {
                const tile = tiles[prevPhase.tileIndex];
                const seconds = skipped
                    ? Math.round(phaseMs / 100) / 10
                    : (tile.rest_after_seconds ?? 0);
                saveThen(
                    () => workoutsApi.recordRestAfter(tile.doc_id, seconds),
                    advance,
                );
            } else {
                advance();
            }
        },
        [phases, tiles, saveTile, saveThen, finish],
    );

    // The countdown loop. Runs only while `status === "running"`; pausing is
    // cancelling the frame, because the deadline lives in a ref and the
    // remainder in state. A manual phase has no deadline: it waits for the
    // Complete set action instead.
    useEffect(() => {
        if (status !== "running" || !phase || phase.kind === "manual") return;

        const tick = () => {
            const remaining = endAtRef.current - performance.now();

            if (remaining > 0) {
                setRemainingMs(remaining);

                const secondsLeft = Math.ceil(remaining / 1000);
                if (
                    secondsLeft <= 3 &&
                    secondsLeft * 1000 < phase.durationMs &&
                    secondsLeft !== lastTickSecondRef.current
                ) {
                    lastTickSecondRef.current = secondsLeft;
                    const pip = COUNTDOWN_PIP[phase.kind];
                    if (pip && audioRef.current) playBeeps(audioRef.current, pip);
                }

                rafRef.current = requestAnimationFrame(tick);
                return;
            }

            // Phase boundary: the phase that just ended banks full, and the
            // overshoot is carried into the next deadline so a busy frame
            // makes the run late once, not every phase.
            advancePast(phase, phaseIndex, phase.durationMs, -remaining, false);
        };

        rafRef.current = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(rafRef.current);
    }, [status, phaseIndex, phase, phases, advancePast]);

    // Keep the screen on while running. A sleeping phone stops the rAF loop
    // and with it the cues.
    useEffect(() => {
        if (status !== "running" || !("wakeLock" in navigator)) return;
        let lock: WakeLockSentinel | null = null;
        let cancelled = false;

        const acquire = () => {
            if (document.visibilityState !== "visible") return;
            navigator.wakeLock
                .request("screen")
                .then((sentinel) => {
                    if (cancelled) void sentinel.release();
                    else lock = sentinel;
                })
                .catch(() => undefined);
        };

        acquire();
        document.addEventListener("visibilitychange", acquire);
        return () => {
            cancelled = true;
            document.removeEventListener("visibilitychange", acquire);
            void lock?.release().catch(() => undefined);
        };
    }, [status]);

    // The AudioContext outlives the run it was created for; close on unmount.
    useEffect(() => {
        return () => {
            audioRef.current?.close().catch(() => undefined);
            audioRef.current = null;
        };
    }, []);

    /**
     * Start at the first incomplete tile — the caller passes exactly those —
     * and proceed through them in order. The snapshot is the tiles *and
     * their target values* as they are now; later edits cannot change the
     * run or a Retry payload.
     */
    const play = useCallback(
        (incomplete: PlayerTile[]) => {
            if (incomplete.length === 0) return;
            ensureAudio();
            const schedule = buildPlayerPhases(incomplete);
            setTiles(incomplete);
            setPhases(schedule);
            setPhaseIndex(0);
            setFailedOp(null);
            wroteAnythingRef.current = false;
            resetBanks();
            lastTickSecondRef.current = -1;
            phaseStartAtRef.current = performance.now();
            endAtRef.current = phaseStartAtRef.current + schedule[0].durationMs;
            setRemainingMs(schedule[0].durationMs);
            setStatus("running");
        },
        // ensureAudio is stable (refs only).
        [resetBanks],
    );

    const pause = useCallback(() => {
        if (status !== "running") return;
        setStatus("paused");
    }, [status]);

    const resume = useCallback(() => {
        if (status !== "paused") return;
        ensureAudio();
        // Re-anchor both clocks: the deadline for the countdown, and the
        // phase's wall-clock start for measurement — paused time is neither
        // countdown nor performance.
        const now = performance.now();
        phaseStartAtRef.current = now - (phase ? phase.durationMs - remainingMs : 0);
        endAtRef.current = now + remainingMs;
        setStatus("running");
    }, [status, phase, remainingMs]);

    /**
     * End the run here and save actual performance through this instant:
     * the banks plus the current phase's elapsed, `ended_early`. Earlier
     * completed tiles stay completed; later tiles remain planned. A Stop in
     * the get-ready or on a manual wait writes nothing.
     */
    const stop = useCallback(() => {
        if (status !== "running" && status !== "paused") return;
        if (!phase || phase.kind === "getReady" || phase.kind === "manual") {
            setPhases([]);
            setTiles([]);
            setStatus("idle");
            return;
        }
        const elapsedMs = Math.max(
            0,
            status === "paused"
                ? phase.durationMs - remainingMs
                : performance.now() - phaseStartAtRef.current,
        );
        const tile = tiles[phase.tileIndex];

        if (phase.kind === "restAfter") {
            const seconds = Math.round(elapsedMs / 100) / 10;
            saveThen(
                () => workoutsApi.recordRestAfter(tile.doc_id, seconds),
                finish,
            );
            return;
        }

        const payload = {
            ...bankedTotals(
                tile,
                phase.kind === "work" ? elapsedMs : 0,
                phase.kind === "rest" ? elapsedMs : 0,
            ),
            ended_early: true,
        };
        saveThen(() => workoutsApi.perform(tile.doc_id, payload), finish);
    }, [status, phase, remainingMs, tiles, bankedTotals, saveThen, finish]);

    /**
     * Skip to the next phase: the current one ends NOW and banks partial.
     * A skipped work rep is a partial rep — its seconds count, the rep does
     * not, and the tile shows it ran short. The divider records partial.
     * Not offered on a manual wait (Complete set is the way through there).
     */
    const skipPhase = useCallback(() => {
        if (status !== "running" || !phase || phase.kind === "manual") return;
        const elapsedMs = Math.max(0, performance.now() - phaseStartAtRef.current);
        advancePast(phase, phaseIndex, elapsedMs, 0, true);
    }, [status, phase, phaseIndex, advancePast]);

    /**
     * Restart the current phase at full. Nothing banks and nothing is
     * written — the phase simply runs again.
     */
    const restartPhase = useCallback(() => {
        if (status !== "running" && status !== "paused") return;
        if (!phase || phase.kind === "manual") return;
        lastTickSecondRef.current = -1;
        if (status === "running") {
            phaseStartAtRef.current = performance.now();
            endAtRef.current = phaseStartAtRef.current + phase.durationMs;
        }
        setRemainingMs(phase.durationMs);
    }, [status, phase]);

    /** The manual tile's one action: the set is done, write it and move on. */
    const completeSet = useCallback(() => {
        if (status !== "running" || !phase || phase.kind !== "manual") return;
        saveTile(phase.tileIndex, () => {
            const nextIndex = phaseIndex + 1;
            if (nextIndex >= phases.length) {
                finish();
                return;
            }
            const next = phases[nextIndex];
            endAtRef.current = performance.now() + next.durationMs;
            lastTickSecondRef.current = -1;
            setPhaseIndex(nextIndex);
            setRemainingMs(next.durationMs);
            setStatus("running");
            if (audioRef.current) {
                playBeeps(
                    audioRef.current,
                    next.kind === "work" ? WORK_START : REST_START,
                );
            }
        });
    }, [status, phase, phaseIndex, phases, saveTile, finish]);

    /** Repeat the write that failed, byte for byte, and continue the run. */
    const retry = useCallback(() => {
        if (status !== "error" || !failedOp) return;
        setFailedOp(null);
        saveThen(failedOp.write, failedOp.afterwards);
    }, [status, failedOp, saveThen]);

    /**
     * Back to a plain day: run state cleared, nothing written. This is the
     * way out of a permanently failed write — the tile stays planned, so it
     * is editable and deletable again, and a later Play starts fresh rather
     * than resuming a run the server never heard about.
     */
    const reset = useCallback(() => {
        setStatus("idle");
        setTiles([]);
        setPhases([]);
        setPhaseIndex(0);
        setRemainingMs(0);
        setFailedOp(null);
    }, []);

    const cancel = useCallback(() => {
        if (status !== "error") return;
        // Invalidate as if the write *had* landed: the failure may be only
        // the lost response, and the tile must not show as planned in that
        // case. Refetching is the only honest answer either way.
        invalidatePerformance();
        reset();
    }, [status, reset, invalidatePerformance]);

    // Re-arm after a finished run: a run that is done must not be terminal.
    // When new incomplete tiles arrive from outside the run (a suggestion, a
    // manual add), the player goes back to idle so Play returns. Adjusted
    // during render rather than in an effect — this is React's "adjust state
    // when a value changes" case, and the guard settles before paint. The
    // `error` state is deliberately excluded — it holds the failed write's
    // snapshot for Retry, and losing that is how work goes unrecorded.
    const incompleteIds = incomplete.map((tile) => tile.doc_id);
    const [seenIncompleteIds, setSeenIncompleteIds] = useState<number[]>([]);
    if (incompleteIds.some((id) => !seenIncompleteIds.includes(id))) {
        setSeenIncompleteIds(incompleteIds);
        if (status === "done") {
            reset();
        }
    }

    const progressLabel = !phase
        ? ""
        : phase.kind === "getReady"
          ? "Get ready"
          : phase.kind === "restAfter"
            ? `Rest after set ${phase.tileIndex + 1}`
            : phase.kind === "manual"
              ? `Set ${phase.tileIndex + 1} · press when done`
              : `Set ${phase.tileIndex + 1} · rep ${phase.rep} / ${phase.repsTotal}`;

    return {
        status,
        phase,
        remainingMs,
        tiles,
        activeTileId,
        progressLabel,
        play,
        pause,
        resume,
        stop,
        completeSet,
        retry,
        cancel,
        reset,
        skipPhase,
        restartPhase,
    };
}
