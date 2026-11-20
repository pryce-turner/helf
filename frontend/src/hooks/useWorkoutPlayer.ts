import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { workoutsApi } from "@/lib/api";
import {
    buildPlayerPhases,
    computeStopActuals,
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

/** The totals a naturally completed tile records, from the snapshot. */
const snapshotTotals = (tile: PlayerTile) => ({
    ended_early: false,
    ...(tile.reps != null ? { completed_reps: tile.reps } : {}),
    ...(tile.work_seconds != null
        ? { actual_work_seconds: tile.work_seconds * (tile.reps ?? 1) }
        : {}),
    ...(tile.rest_seconds != null
        ? { actual_rest_seconds: tile.rest_seconds * ((tile.reps ?? 1) - 1) }
        : {}),
});

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

export function useWorkoutPlayer() {
    const queryClient = useQueryClient();

    const [status, setStatus] = useState<PlayerStatus>("idle");
    const [tiles, setTiles] = useState<PlayerTile[]>([]);
    const [phases, setPhases] = useState<PlayerPhase[]>([]);
    const [phaseIndex, setPhaseIndex] = useState(0);
    const [remainingMs, setRemainingMs] = useState(0);
    const [failedOp, setFailedOp] = useState<FailedOp | null>(null);

    const endAtRef = useRef(0);
    const rafRef = useRef(0);
    const audioRef = useRef<AudioContext | null>(null);
    const lastTickSecondRef = useRef(-1);
    // Anything written this run: a Stop that wrote shows "done", one that
    // wrote nothing simply resets — a run abandoned before any work is not
    // a result.
    const wroteAnythingRef = useRef(false);

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

    const saveTile = useCallback(
        (tileIndex: number, afterwards: () => void) => {
            const tile = tiles[tileIndex];
            saveThen(() => workoutsApi.perform(tile.doc_id, snapshotTotals(tile)), afterwards);
        },
        [tiles, saveThen],
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

            // Phase boundary. The overshoot is carried into the next deadline
            // so a busy frame makes the run late once, not every phase.
            const overshoot = -remaining;
            const nextIndex = phaseIndex + 1;
            const prev = phase;

            const advance = () => {
                if (nextIndex >= phases.length) {
                    setRemainingMs(0);
                    finish();
                    return;
                }
                const next = phases[nextIndex];
                endAtRef.current = performance.now() + next.durationMs - overshoot;
                lastTickSecondRef.current = -1;
                setPhaseIndex(nextIndex);
                setRemainingMs(next.durationMs - overshoot);
                // Reached from a save as well as from the plain loop: the
                // countdown only runs in `running`.
                setStatus("running");
                if (audioRef.current) {
                    playBeeps(
                        audioRef.current,
                        next.kind === "work" ? WORK_START : REST_START,
                    );
                }
            };

            // A tile's performance writes when its last work rep ends; the
            // divider's when the rest-after runs out. Both before advancing,
            // so nothing advances unsaved.
            const tileFinished = prev.kind === "work" && prev.rep === prev.repsTotal;
            if (tileFinished) {
                saveTile(prev.tileIndex, advance);
            } else if (prev.kind === "restAfter") {
                const tile = tiles[prev.tileIndex];
                saveThen(
                    () =>
                        workoutsApi.recordRestAfter(
                            tile.doc_id,
                            tile.rest_after_seconds ?? 0,
                        ),
                    advance,
                );
            } else {
                advance();
            }
        };

        rafRef.current = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(rafRef.current);
    }, [status, phaseIndex, phase, phases, tiles, saveTile, saveThen, finish]);

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
            lastTickSecondRef.current = -1;
            endAtRef.current = performance.now() + schedule[0].durationMs;
            setRemainingMs(schedule[0].durationMs);
            setStatus("running");
        },
        // ensureAudio is stable (refs only).
        [],
    );

    const pause = useCallback(() => {
        if (status !== "running") return;
        setStatus("paused");
    }, [status]);

    const resume = useCallback(() => {
        if (status !== "paused") return;
        ensureAudio();
        endAtRef.current = performance.now() + remainingMs;
        setStatus("running");
    }, [status, remainingMs]);

    /**
     * End the run here and save actual performance through this instant.
     * Earlier completed tiles stay completed; later tiles remain planned. A
     * Stop in the get-ready or on a manual wait writes nothing.
     */
    const stop = useCallback(() => {
        if (status !== "running" && status !== "paused") return;
        const elapsedMs = phase ? Math.max(0, phase.durationMs - remainingMs) : 0;
        const actuals = computeStopActuals(tiles, phases, phaseIndex, elapsedMs);

        if (actuals.kind === "none") {
            setPhases([]);
            setTiles([]);
            setStatus("idle");
            return;
        }
        if (actuals.kind === "restAfter") {
            const tile = tiles[actuals.tileIndex];
            saveThen(
                () => workoutsApi.recordRestAfter(tile.doc_id, actuals.seconds),
                finish,
            );
            return;
        }
        const tile = tiles[actuals.tileIndex];
        saveThen(
            () =>
                workoutsApi.perform(tile.doc_id, {
                    ended_early: true,
                    completed_reps: actuals.completedReps,
                    actual_work_seconds: actuals.actualWorkSeconds,
                    actual_rest_seconds: actuals.actualRestSeconds,
                }),
            finish,
        );
    }, [status, phase, phases, phaseIndex, remainingMs, tiles, saveThen, finish]);

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
    };
}
