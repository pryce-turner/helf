import type { Exercise } from "@/types/exercise";

/**
 * Shared set-tile helpers (plan 0018): the seconds formatting the tiles and
 * rest dividers read, and the defaults a new tile takes from its exercise.
 */

/** `m:ss`, whole seconds. */
export const formatSeconds = (seconds: number): string => {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
};

/**
 * The defaults a tile takes from its exercise at creation. Enabled with a
 * null default starts blank; a disabled group's default is never applied.
 * Once the tile exists its values are its own — later edits to the exercise
 * do not reach back.
 */
export const defaultsFromExercise = (exercise: Exercise) => ({
  reps: exercise.reps_enabled ? exercise.default_reps : null,
  weight: exercise.weight_enabled ? exercise.default_weight_lb : null,
  distance: exercise.distance_enabled ? exercise.default_distance : null,
  distance_unit: exercise.distance_enabled
    ? exercise.default_distance_unit
    : null,
  work_seconds: exercise.time_enabled ? exercise.default_work_seconds : null,
  rest_seconds: exercise.time_enabled ? exercise.default_rest_seconds : null,
  rest_after_seconds: exercise.time_enabled
    ? exercise.default_rest_after_seconds
    : null,
});

/**
 * The actuals a natural completion claims, derived from the tile's targets
 * as **totals** — two 40s reps are 80s of work, and the per-rep rest runs
 * only between reps, never after the last. Mirrors the server's
 * `_derive_actuals`, so the optimistic tick shows what the write will say.
 */
export const derivedActuals = (tile: {
  reps: number | null;
  work_seconds: number | null;
  rest_seconds: number | null;
}) => {
  // `|| 1`, mirroring the server's `workout.reps or 1`: an uncounted or zero
  // target is one bout, never zero seconds of work.
  const reps = tile.reps || 1;
  return {
    completed_reps: tile.reps,
    actual_work_seconds:
      tile.work_seconds != null ? tile.work_seconds * reps : null,
    actual_rest_seconds:
      tile.rest_seconds != null ? tile.rest_seconds * (reps - 1) : null,
    ended_early: false,
  };
};

/**
 * The timed work a workout holds, in seconds: every tile with a work time,
 * counted as a total across its reps (`derivedActuals`' rule — 6 × 10s holds
 * are 60s). A performed tile counts what was measured, so a stopped set adds
 * what was actually done rather than its target. Rests are not work and are
 * left out.
 */
export const timedWorkSeconds = (
  tiles: {
    reps: number | null;
    work_seconds: number | null;
    rest_seconds: number | null;
    completed_at: string | null;
    actual_work_seconds: number | null;
  }[],
): number =>
  tiles.reduce((total, tile) => {
    if (tile.completed_at && tile.actual_work_seconds != null) {
      return total + tile.actual_work_seconds;
    }
    return total + (derivedActuals(tile).actual_work_seconds ?? 0);
  }, 0);

/** A duration total: `m:ss`, or `h:mm:ss` from an hour up. */
export const formatDuration = (seconds: number): string => {
  const whole = Math.round(seconds);
  if (whole < 3600) return formatSeconds(whole);
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
};
