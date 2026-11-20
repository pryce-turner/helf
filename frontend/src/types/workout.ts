export interface Workout {
  doc_id: number;
  date: string;
  exercise: string;
  category: string;
  weight: number | null;
  weight_unit: string;
  reps: number | null;
  distance: number | null;
  distance_unit: string | null;
  /** Legacy free-form duration, kept for old rows; new tiles use the numeric fields. */
  time: string | null;
  comment: string | null;
  completed_at: string | null;
  /**
   * Whether *this set* was mobility work.
   *
   * Not a property of the exercise: the same movement is a lift in one row and
   * a loaded stretch in the next, which is why the flag moved off `exercises`.
   * The most recent day carrying any of these is what the agent reads to write
   * the next mobility session, so clearing one changes what it sees.
   */
  is_mobility: boolean;
  order: number;
  created_at: string;
  updated_at: string;
  /**
   * Target timing (plan 0018): what the tile asks the player to run.
   * `rest_after_seconds` belongs to this tile and renders as the rest divider
   * after it — not a row of its own.
   */
  work_seconds: number | null;
  rest_seconds: number | null;
  rest_after_seconds: number | null;
  /**
   * Actual performance, null until the tile is performed. Written only by the
   * performance paths (the player, or the completion tick, which derives them
   * from the targets), never by an edit.
   */
  completed_reps: number | null;
  actual_work_seconds: number | null;
  actual_rest_seconds: number | null;
  actual_rest_after_seconds: number | null;
  /** Natural completion vs Stop. A stopped tile stays complete. */
  ended_early: boolean;
}

export interface WorkoutCreate {
  date: string;
  exercise: string;
  category: string;
  weight?: number | null;
  weight_unit?: string;
  reps?: number | null;
  distance?: number | null;
  distance_unit?: string | null;
  time?: string | null;
  comment?: string | null;
  completed_at?: string | null;
  /** Omit to leave a set's flag alone; the backend only writes it when sent. */
  is_mobility?: boolean;
  /**
   * Target timing — fillable only for exercises with Time enabled; the
   * backend nulls the rest, so a stale client cannot write one the movement
   * does not take.
   */
  work_seconds?: number | null;
  rest_seconds?: number | null;
  rest_after_seconds?: number | null;
  /**
   * Omit to have the server place the set directly below the day's
   * bottom-most completed set (appended if nothing is completed).
   */
  order?: number;
}

/**
 * One tile's performance as measured by the day player (plan 0018). Natural
 * completion sends only `ended_early: false` and the server derives the full
 * actuals from the targets; a Stop sends what was measured. The server
 * assigns `completed_at` and the date — work is logged on the day it is run.
 */
export interface WorkoutPerform {
  ended_early?: boolean;
  completed_reps?: number | null;
  actual_work_seconds?: number | null;
  actual_rest_seconds?: number | null;
}

/** The rest divider after a tile, whole or partial, written to that tile. */
export interface WorkoutRestAfter {
  actual_rest_after_seconds: number;
}

export interface CalendarResponse {
  year: number;
  month: number;
  /** Performed tiles per day. A planned tile counts for nothing (plan 0018). */
  counts: Record<string, number>;
}
