/**
 * Trendlines for the body charts, from a straight fit to every point.
 *
 * One smoothing knob, 0..SMOOTHING_MAX, and one method all the way along it:
 * a local linear fit around each day, weighted by a tricube window whose
 * half-width shrinks as the knob rises.
 *
 * - 0 is ordinary least squares through every reading: one straight line.
 * - In between, the window narrows from ~3x the period down to half a day.
 *   Away from the edges that is a weighted moving average; at the edges a
 *   local *line* keeps the curve from flattening the way a plain moving
 *   average does, where its window runs out of points on one side.
 * - SMOOTHING_MAX leaves only same-day readings inside each window, so the
 *   line passes through every day: through the reading, or the mean of a
 *   day's readings when there are several. Joining same-day readings to each
 *   other would only draw a vertical zigzag, and every reading is still
 *   plotted as its own dot.
 *
 * The line is evaluated once per distinct day, so a chart joins those values
 * and nothing else. Pure functions over numbers - no React, no Recharts - so
 * the whole thing is tested in `trend.test.ts`.
 */

export interface TrendPoint {
    /** Milliseconds since the epoch, as Recharts' time axis wants. */
    t: number;
    y: number;
}

export const SMOOTHING_MAX = 100;

const DAY_MS = 86_400_000;
/** Narrowest window half-width: under a day, so only that day remains. */
const MIN_HALF_WIDTH_DAYS = 0.5;
/**
 * Widest window as a multiple of the data's span. Tricube weights then stay
 * above (1 - (1/3)^3)^3 = 0.89 across the whole period, so the first step off
 * 0 is barely distinguishable from the straight fit it leaves.
 */
const MAX_HALF_WIDTH_SPANS = 3;

/** Window half-width in days for a smoothing setting, or null for a straight fit. */
export const halfWidthDays = (
    smoothing: number,
    spanDays: number,
): number | null => {
    const s = Math.min(Math.max(smoothing, 0), SMOOTHING_MAX) / SMOOTHING_MAX;
    if (s === 0) return null;
    const widest = Math.max(spanDays * MAX_HALF_WIDTH_SPANS, MIN_HALF_WIDTH_DAYS);
    // Geometric, so each step of the slider changes the window by the same
    // ratio: the narrow end, where the shape changes most, gets most of the
    // travel rather than the last few pixels.
    return widest * Math.pow(MIN_HALF_WIDTH_DAYS / widest, s);
};

/** Weighted least-squares line through (x, y), evaluated at x0. */
const fitAt = (
    xs: number[],
    ys: number[],
    weights: number[],
    x0: number,
): number => {
    let sw = 0;
    let sx = 0;
    let sy = 0;
    for (let i = 0; i < xs.length; i++) {
        sw += weights[i];
        sx += weights[i] * xs[i];
        sy += weights[i] * ys[i];
    }
    const mx = sx / sw;
    const my = sy / sw;
    let sxx = 0;
    let sxy = 0;
    for (let i = 0; i < xs.length; i++) {
        const dx = xs[i] - mx;
        sxx += weights[i] * dx * dx;
        sxy += weights[i] * dx * (ys[i] - my);
    }
    // Every weighted reading on one day: there is no slope to fit, only a level.
    if (sxx < 1e-12) return my;
    return my + (sxy / sxx) * (x0 - mx);
};

/**
 * The trendline for `points` at `smoothing`, one value per distinct `t`,
 * sorted by `t`. Non-finite values are dropped; fewer than one usable point
 * gives an empty line.
 */
export const trendLine = (
    points: TrendPoint[],
    smoothing: number,
): TrendPoint[] => {
    const clean = points
        .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.y))
        .sort((a, b) => a.t - b.t);
    if (clean.length === 0) return [];

    // Days from the first reading, so the sums stay small whatever the epoch.
    const t0 = clean[0].t;
    const xs = clean.map((p) => (p.t - t0) / DAY_MS);
    const ys = clean.map((p) => p.y);
    const at = [...new Set(clean.map((p) => p.t))];
    const span = xs[xs.length - 1];

    const h = halfWidthDays(smoothing, span);
    if (h === null) {
        const ones = xs.map(() => 1);
        return at.map((t) => ({ t, y: fitAt(xs, ys, ones, (t - t0) / DAY_MS) }));
    }

    return at.map((t) => {
        const x0 = (t - t0) / DAY_MS;
        const wx: number[] = [];
        const wy: number[] = [];
        const w: number[] = [];
        for (let i = 0; i < xs.length; i++) {
            const d = Math.abs(xs[i] - x0) / h;
            if (d >= 1) continue;
            const k = 1 - d * d * d;
            wx.push(xs[i]);
            wy.push(ys[i]);
            w.push(k * k * k);
        }
        // x0 is itself a reading's day, so the window always holds at least it.
        return { t, y: fitAt(wx, wy, w, x0) };
    });
};

/** How a smoothing setting reads in words, for the label beside the slider. */
export const describeSmoothing = (smoothing: number, spanDays: number): string => {
    if (smoothing <= 0) return "Straight line";
    if (smoothing >= SMOOTHING_MAX) return "Every day";
    const h = halfWidthDays(smoothing, spanDays) ?? 0;
    if (h >= spanDays) return "Nearly straight";
    // The tricube window's full width is 2h, but its weight is concentrated
    // in the middle; h itself is the honest "how far a reading reaches".
    return `±${Math.max(1, Math.round(h))} day${Math.round(h) <= 1 ? "" : "s"}`;
};
