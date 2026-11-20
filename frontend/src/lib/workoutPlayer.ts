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


