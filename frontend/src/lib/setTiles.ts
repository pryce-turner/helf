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
