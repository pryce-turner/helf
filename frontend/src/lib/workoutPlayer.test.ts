/**
 * The phase builder and stop-actuals computation, pure and so testable
 * without a frame of the rAF loop. The mapping from the old interval timer
 * (plan 0018): work+rest is one rep, exercises are reps in a set, a round is
 * one set tile, and the round reset is the rest-after on the preceding tile.
 */
import { describe, expect, it } from "vitest";
import {
    GET_READY_MS,
    buildPlayerPhases,
    computeStopActuals,
    type PlayerTile,
} from "./workoutPlayer";
import { derivedActuals } from "./setTiles";

describe("derivedActuals", () => {
    it("derives totals, not per-rep values, mirroring the server", () => {
        // Two 40s reps is 80s of work; the rest runs only between them.
        expect(
            derivedActuals({ reps: 2, work_seconds: 40, rest_seconds: 20 }),
        ).toEqual({
            completed_reps: 2,
            actual_work_seconds: 80,
            actual_rest_seconds: 20,
            ended_early: false,
        });
    });

    it("treats an uncounted timed set as one bout with no per-rep rest", () => {
        expect(
            derivedActuals({ reps: null, work_seconds: 30, rest_seconds: 20 }),
        ).toEqual({
            completed_reps: null,
            actual_work_seconds: 30,
            actual_rest_seconds: 0,
            ended_early: false,
        });
    });

    it("keeps absent fields absent rather than inventing zeroes", () => {
        expect(
            derivedActuals({ reps: 5, work_seconds: null, rest_seconds: null }),
        ).toEqual({
            completed_reps: 5,
            actual_work_seconds: null,
            actual_rest_seconds: null,
            ended_early: false,
        });
    });
});

const tile = (overrides: Partial<PlayerTile> = {}): PlayerTile => ({
    doc_id: 1,
    exercise: "Farmer Carry",
    reps: 2,
    work_seconds: 40,
    rest_seconds: 20,
    rest_after_seconds: 15,
    ...overrides,
});

describe("buildPlayerPhases", () => {
    it("opens on a single get-ready, then work and rest per rep", () => {
        const phases = buildPlayerPhases([tile()]);

        expect(phases[0]).toMatchObject({ kind: "getReady", durationMs: GET_READY_MS });
        expect(phases.slice(1).map((p) => [p.kind, p.rep])).toEqual([
            ["work", 1],
            ["rest", 1],
            ["work", 2],
        ]);
    });

    it("plays no per-rep rest after the last rep, and no rest-after after the last tile", () => {
        const phases = buildPlayerPhases([tile(), tile({ doc_id: 2 })]);

        const kinds = phases.map((p) => p.kind);
        // Rest-after belongs between the two tiles, not after either's reps
        // and never after the final one.
        expect(kinds).toEqual([
            "getReady",
            "work", "rest", "work",
            "restAfter",
            "work", "rest", "work",
        ]);
    });

    it("skips a zero rest and a zero rest-after entirely", () => {
        const phases = buildPlayerPhases([
            tile({ rest_seconds: 0, rest_after_seconds: 0, doc_id: 1 }),
            tile({ doc_id: 2 }),
        ]);

        // The first tile runs its two reps back to back; the second keeps
        // its own rest, and no divider sits between them.
        expect(phases.map((p) => p.kind)).toEqual([
            "getReady", "work", "work", "work", "rest", "work",
        ]);
    });

    it("waits for a manual completion on an untimed tile rather than inventing a duration", () => {
        const phases = buildPlayerPhases([
            tile({ work_seconds: null, reps: 8, rest_seconds: null }),
        ]);

        expect(phases).toHaveLength(2);
        expect(phases[1]).toMatchObject({ kind: "manual", tileIndex: 0, durationMs: 0 });
    });

    it("treats a timed tile with no reps as one bout", () => {
        const phases = buildPlayerPhases([tile({ reps: null })]);

        expect(phases.slice(1).map((p) => p.kind)).toEqual(["work"]);
        expect(phases[1].repsTotal).toBe(1);
    });
});

describe("computeStopActuals", () => {
    const tiles = [tile(), tile({ doc_id: 2 })];

    it("writes nothing during get-ready", () => {
        expect(computeStopActuals(tiles, buildPlayerPhases(tiles), 0, 2000)).toEqual({
            kind: "none",
        });
    });

    it("mid-work: the partial rep counts its seconds, not the rep", () => {
        // Phase 1 is the first tile's first work rep; 12s in.
        expect(computeStopActuals(tiles, buildPlayerPhases(tiles), 1, 12_000)).toEqual({
            kind: "tile",
            tileIndex: 0,
            completedReps: 0,
            actualWorkSeconds: 12,
            actualRestSeconds: 0,
        });
    });

    it("mid-rest: the work of the completed reps plus the partial rest", () => {
        // Phase 2 is the rest after rep 1; 7s in.
        expect(computeStopActuals(tiles, buildPlayerPhases(tiles), 2, 7_000)).toEqual({
            kind: "tile",
            tileIndex: 0,
            completedReps: 1,
            actualWorkSeconds: 40,
            actualRestSeconds: 7,
        });
    });

    it("during a rest divider: only the preceding tile's rest-after, partial", () => {
        // Phase 4 is the restAfter of tile 0; 6s in.
        expect(computeStopActuals(tiles, buildPlayerPhases(tiles), 4, 6_000)).toEqual({
            kind: "restAfter",
            tileIndex: 0,
            seconds: 6,
        });
    });

    it("on a manual tile: nothing measured, the tile stays planned", () => {
        const manual = [tile({ work_seconds: null, reps: 8 })];
        expect(computeStopActuals(manual, buildPlayerPhases(manual), 1, 30_000)).toEqual({
            kind: "none",
        });
    });

    it("on the second tile: the first is already saved and untouched", () => {
        // getReady, then 3 phases of tile 0's reps, its restAfter, then tile
        // 1's first work and rest: phase 7 is the second tile's second work
        // rep, 25s in.
        expect(computeStopActuals(tiles, buildPlayerPhases(tiles), 7, 25_000)).toEqual({
            kind: "tile",
            tileIndex: 1,
            completedReps: 1,
            actualWorkSeconds: 40 + 25,
            actualRestSeconds: 20,
        });
    });
});
