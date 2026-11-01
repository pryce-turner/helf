/**
 * Cardio: the unit vocabulary and the time format (plan 0017).
 *
 * `CARDIO_UNITS` mirrors the CHECK on `exercises.cardio_unit` and
 * `workouts.amount_unit` (a5f701728b12). The database is the rule; this is the
 * copy that decides what the picker offers, and adding a unit means a
 * migration first.
 */

export const CARDIO_UNITS = [
    { value: "miles", label: "Miles", short: "mi" },
    { value: "km", label: "Kilometers", short: "km" },
    { value: "meters", label: "Meters", short: "m" },
    { value: "floors", label: "Floors", short: "floors" },
    { value: "steps", label: "Steps", short: "steps" },
    { value: "kcal", label: "Calories", short: "kcal" },
] as const;

export type CardioUnit = (typeof CARDIO_UNITS)[number]["value"];

/** How a set's amount reads in a chip: "3.1 mi", "60 floors". */
export const formatAmount = (amount: number, unit: string | null): string => {
    const short = CARDIO_UNITS.find((u) => u.value === unit)?.short ?? unit ?? "";
    return `${amount} ${short}`.trim();
};

/**
 * What the time field accepts: minutes, m:ss or h:mm:ss. A bare number is
 * minutes because that is how a cardio session is spoken of — "45 on the
 * bike" is never 45 seconds. Shared with the input's `pattern`, so the form
 * refuses to submit what this would refuse to read.
 */
export const DURATION_PATTERN = "\\d+(:[0-5]\\d){0,2}";
const DURATION_RE = new RegExp(`^${DURATION_PATTERN}$`);

/** Whole seconds, or null for an empty field *or* one it cannot read. */
export const parseDuration = (text: string): number | null => {
    const trimmed = text.trim();
    if (!DURATION_RE.test(trimmed)) return null;
    const parts = trimmed.split(":").map(Number);
    if (parts.length === 1) return parts[0] * 60;
    return parts.reduce((total, part) => total * 60 + part, 0);
};

export const formatDuration = (seconds: number | null | undefined): string => {
    if (seconds == null) return "";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    const ss = String(s).padStart(2, "0");
    return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
};
