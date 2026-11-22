import { describe, expect, it } from "vitest";
import { formatDuration, timedWorkSeconds } from "./setTiles";

const tile = (overrides: Record<string, unknown> = {}) => ({
    reps: null,
    work_seconds: null,
    rest_seconds: null,
    completed_at: null,
    actual_work_seconds: null,
    ...overrides,
});

describe("timedWorkSeconds", () => {
    it("totals each timed tile across its reps, and skips untimed ones", () => {
        expect(
            timedWorkSeconds([
                tile({ reps: 6, work_seconds: 10, rest_seconds: 5 }),
                tile({ reps: 2, work_seconds: 10 }),
                tile({ reps: 5 }), // a lift: no work time
            ]),
        ).toBe(80);
    });

    it("counts an uncounted timed tile as one bout", () => {
        expect(timedWorkSeconds([tile({ work_seconds: 45 })])).toBe(45);
    });

    it("counts what was measured on a performed tile", () => {
        expect(
            timedWorkSeconds([
                tile({ reps: 6, work_seconds: 10, completed_at: "x", actual_work_seconds: 42.5 }),
            ]),
        ).toBe(42.5);
    });

    it("is zero when nothing is timed", () => {
        expect(timedWorkSeconds([tile({ reps: 5 })])).toBe(0);
    });
});

describe("formatDuration", () => {
    it("reads m:ss under an hour and h:mm:ss over", () => {
        expect(formatDuration(600)).toBe("10:00");
        expect(formatDuration(3725)).toBe("1:02:05");
    });
});
