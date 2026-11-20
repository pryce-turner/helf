/**
 * The day player's schedule, pure.
 *
 * A run is one get-ready, then per tile: its work reps with per-rep rests
 * between them (never after the last rep — the rest-after divider handles
 * that boundary), a manual wait for an untimed tile, and the rest-after
 * divider between tiles (never after the last one, plan 0018). Building it
 * as a list — rather than computing the phase from elapsed time — is what
 * keeps the hook's state machine trivial: it only ever asks "what is next".
 */

export interface PlayerTile {
    doc_id: number;
    exercise: string;
    reps: number | null;
    work_seconds: number | null;
    rest_seconds: number | null;
    rest_after_seconds: number | null;
}

export type PhaseKind = "getReady" | "work" | "rest" | "restAfter" | "manual";

export interface PlayerPhase {
    kind: PhaseKind;
    /** Index into the snapshot's tile list. */
    tileIndex: number;
    /** 1-based rep for work/rest phases; 0 elsewhere. */
    rep: number;
    /** The tile's rep count: 1 for a manual wait or an uncounted timed bout. */
    repsTotal: number;
    /** 0 for the manual wait, which has no duration of its own. */
    durationMs: number;
}

/** The lead-in before the first work of a run: once, never between tiles. */
export const GET_READY_MS = 5000;

export function buildPlayerPhases(tiles: PlayerTile[]): PlayerPhase[] {
    const phases: PlayerPhase[] = [
        { kind: "getReady", tileIndex: 0, rep: 0, repsTotal: 0, durationMs: GET_READY_MS },
    ];

    tiles.forEach((tile, tileIndex) => {
        if (tile.work_seconds == null) {
            // Untimed: the player must not invent a duration, so it waits
            // for the manual Complete set action.
            phases.push({ kind: "manual", tileIndex, rep: 1, repsTotal: 1, durationMs: 0 });
        } else {
            const reps = tile.reps ?? 1;
            for (let rep = 1; rep <= reps; rep++) {
                phases.push({
                    kind: "work",
                    tileIndex,
                    rep,
                    repsTotal: reps,
                    durationMs: tile.work_seconds * 1000,
                });
                // Per-rep rest follows each work rep except the last in the
                // set — a rest there would double up with the rest-after.
                if (rep < reps && (tile.rest_seconds ?? 0) > 0) {
                    phases.push({
                        kind: "rest",
                        tileIndex,
                        rep,
                        repsTotal: reps,
                        durationMs: (tile.rest_seconds ?? 0) * 1000,
                    });
                }
            }
        }

        // Rest after the final tile is not played; a zero rest-after is no
        // rest, just absent.
        if (tileIndex < tiles.length - 1 && (tile.rest_after_seconds ?? 0) > 0) {
            phases.push({
                kind: "restAfter",
                tileIndex,
                rep: 0,
                repsTotal: 0,
                durationMs: (tile.rest_after_seconds ?? 0) * 1000,
            });
        }
    });

    return phases;
}

export type StopActuals =
    /** Get-ready, or a manual wait: nothing measured, nothing written. */
    | { kind: "none" }
    /** Stopped on a tile: mark it completed early with the measured actuals. */
    | {
          kind: "tile";
          tileIndex: number;
          completedReps: number;
          actualWorkSeconds: number;
          actualRestSeconds: number;
      }
    /** Stopped in a divider: only the preceding tile's rest-after, partial. */
    | { kind: "restAfter"; tileIndex: number; seconds: number };

/**
 * What a Stop means for the tile in front of it.
 *
 * Paused wall time is excluded by the caller passing the phase's *banked*
 * elapsed, and the get-ready is excluded by shape — it is not work. A
 * partial work rep contributes its elapsed seconds to `actualWorkSeconds`
 * but does not increment `completedReps` (plan 0018).
 */
export function computeStopActuals(
    tiles: PlayerTile[],
    phases: PlayerPhase[],
    phaseIndex: number,
    phaseElapsedMs: number,
): StopActuals {
    const phase = phases[phaseIndex];
    if (!phase || phase.kind === "getReady" || phase.kind === "manual") {
        return { kind: "none" };
    }
    const tile = tiles[phase.tileIndex];
    if (!tile) return { kind: "none" };

    if (phase.kind === "restAfter") {
        return {
            kind: "restAfter",
            tileIndex: phase.tileIndex,
            seconds: Math.round(phaseElapsedMs / 100) / 10,
        };
    }

    // Sum the tile's fully completed phases from the schedule rather than
    // counting on the current one: work of the reps behind this phase, rest
    // of the rests behind it, plus whatever the current phase has measured.
    let completedReps = 0;
    let workMs = 0;
    let restMs = 0;
    for (let i = 0; i < phases.length; i++) {
        const p = phases[i];
        if (p.tileIndex !== phase.tileIndex) continue;
        if (i < phaseIndex) {
            if (p.kind === "work") {
                completedReps += 1;
                workMs += p.durationMs;
            } else if (p.kind === "rest") {
                restMs += p.durationMs;
            }
        } else if (i === phaseIndex) {
            if (p.kind === "work") workMs += phaseElapsedMs;
            else if (p.kind === "rest") restMs += phaseElapsedMs;
        }
    }

    return {
        kind: "tile",
        tileIndex: phase.tileIndex,
        completedReps,
        actualWorkSeconds: Math.round(workMs / 100) / 10,
        actualRestSeconds: Math.round(restMs / 100) / 10,
    };
}
