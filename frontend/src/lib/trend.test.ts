import { describe, expect, it } from "vitest";

import {
    SMOOTHING_MAX,
    describeSmoothing,
    halfWidthDays,
    trendLine,
    type TrendPoint,
} from "./trend";

const DAY = 86_400_000;
const T0 = Date.UTC(2026, 0, 1);
const day = (n: number, y: number): TrendPoint => ({ t: T0 + n * DAY, y });

// Irregular days, noisy values, one day read twice: the shape the scale gives.
const READINGS = [
    day(0, 190.2),
    day(1, 189.6),
    day(1, 190.4),
    day(4, 189.1),
    day(5, 189.9),
    day(9, 188.3),
    day(12, 188.8),
    day(13, 187.6),
    day(20, 187.9),
];

const SETTINGS = [0, 1, 10, 25, 50, 75, 90, 99, SMOOTHING_MAX];

/** Plain OLS over every reading, written out independently of trend.ts. */
const ols = (pts: TrendPoint[]) => {
    const n = pts.length;
    const xs = pts.map((p) => (p.t - T0) / DAY);
    const mx = xs.reduce((a, b) => a + b, 0) / n;
    const my = pts.reduce((a, p) => a + p.y, 0) / n;
    let sxx = 0;
    let sxy = 0;
    pts.forEach((p, i) => {
        sxx += (xs[i] - mx) ** 2;
        sxy += (xs[i] - mx) * (p.y - my);
    });
    const slope = sxy / sxx;
    return (t: number) => my + slope * ((t - T0) / DAY - mx);
};

describe("trendLine", () => {
    it("is the least-squares line through every reading at 0", () => {
        const fit = ols(READINGS);
        const line = trendLine(READINGS, 0);
        for (const p of line) expect(p.y).toBeCloseTo(fit(p.t), 10);
    });

    it("is straight at 0: equal steps in time make equal steps in value", () => {
        const line = trendLine(READINGS, 0);
        const slopes = line
            .slice(1)
            .map((p, i) => (p.y - line[i].y) / (p.t - line[i].t));
        for (const s of slopes) expect(s).toBeCloseTo(slopes[0], 12);
    });

    it("passes through every day at the far end, averaging a day read twice", () => {
        const line = trendLine(READINGS, SMOOTHING_MAX);
        expect(line.map((p) => p.t)).toEqual([
            ...new Set(READINGS.map((p) => p.t)),
        ]);
        expect(line[0].y).toBeCloseTo(190.2, 10);
        expect(line[1].y).toBeCloseTo((189.6 + 190.4) / 2, 10);
        expect(line.at(-1)!.y).toBeCloseTo(187.9, 10);
    });

    it("gives one value per distinct day, in time order, at every setting", () => {
        const shuffled = [...READINGS].reverse();
        const days = [...new Set(READINGS.map((p) => p.t))];
        for (const s of SETTINGS) {
            expect(trendLine(shuffled, s).map((p) => p.t)).toEqual(days);
        }
    });

    it("reproduces data that is already a line, at every setting", () => {
        // A local *linear* fit has no bias on a straight series - the property
        // that keeps the ends from flattening the way a moving average does.
        const straight = READINGS.map((p) => ({
            t: p.t,
            y: 200 - 0.25 * ((p.t - T0) / DAY),
        }));
        for (const s of SETTINGS) {
            for (const p of trendLine(straight, s)) {
                expect(p.y).toBeCloseTo(200 - 0.25 * ((p.t - T0) / DAY), 9);
            }
        }
    });

    it("bends further from the straight fit as smoothing rises", () => {
        const fit = ols(READINGS);
        const distance = (s: number) =>
            trendLine(READINGS, s).reduce((a, p) => a + (p.y - fit(p.t)) ** 2, 0);
        const ds = [0, 25, 50, 75, SMOOTHING_MAX].map(distance);
        expect(ds[0]).toBeCloseTo(0, 12);
        for (let i = 1; i < ds.length; i++) {
            expect(ds[i]).toBeGreaterThanOrEqual(ds[i - 1] - 1e-9);
        }
        expect(ds.at(-1)!).toBeGreaterThan(0.5);
    });

    it("barely moves on the first step off a straight line", () => {
        const a = trendLine(READINGS, 0);
        const b = trendLine(READINGS, 1);
        a.forEach((p, i) => expect(Math.abs(p.y - b[i].y)).toBeLessThan(0.05));
    });

    it("copes with nothing, one reading, one day, and junk values", () => {
        expect(trendLine([], 50)).toEqual([]);
        expect(trendLine([day(3, 180)], 0)).toEqual([day(3, 180)]);
        expect(trendLine([day(3, 180), day(3, 182)], 0)).toEqual([day(3, 181)]);
        expect(
            trendLine([day(0, 180), day(1, NaN), day(2, 182)], SMOOTHING_MAX),
        ).toEqual([day(0, 180), day(2, 182)]);
    });
});

describe("halfWidthDays / describeSmoothing", () => {
    it("narrows monotonically from several spans down to half a day", () => {
        expect(halfWidthDays(0, 30)).toBeNull();
        expect(halfWidthDays(1, 30)!).toBeGreaterThan(80);
        expect(halfWidthDays(SMOOTHING_MAX, 30)).toBeCloseTo(0.5, 12);
        let last = Infinity;
        for (let s = 1; s <= SMOOTHING_MAX; s++) {
            const h = halfWidthDays(s, 30)!;
            expect(h).toBeLessThan(last);
            last = h;
        }
    });

    it("names the ends and the window in between", () => {
        expect(describeSmoothing(0, 30)).toBe("Straight line");
        expect(describeSmoothing(SMOOTHING_MAX, 30)).toBe("Every day");
        expect(describeSmoothing(5, 30)).toBe("Nearly straight");
        expect(describeSmoothing(60, 30)).toMatch(/^±\d+ days?$/);
    });
});
