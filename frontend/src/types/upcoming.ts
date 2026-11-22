export interface UpcomingWorkout {
  doc_id: number;
  session: number;
  /** Whether this prescribed set is mobility work; transfer carries it onto the logged set. */
  is_mobility: boolean;
  exercise: string;
  category: string;
  weight: number | null;
  weight_unit: string;
  reps: number | null;
  distance: number | null;
  distance_unit: string | null;
  /** Legacy free-form duration; read-only — new rows carry `work_seconds`. */
  time: string | null;
  comment: string | null;
  /** The set tile's target timing (plan 0021), carried onto the day at transfer. */
  work_seconds: number | null;
  rest_seconds: number | null;
  rest_after_seconds: number | null;
  created_at: string;
}

export interface UpcomingWorkoutCreate {
  session: number;
  exercise: string;
  category: string;
  is_mobility?: boolean;
  weight?: number | null;
  weight_unit?: string;
  reps?: number | null;
  distance?: number | null;
  distance_unit?: string | null;
  time?: string | null;
  comment?: string | null;
}

/**
 * One session of the upcoming queue, with its plan metadata if it has any.
 *
 * The queue is one list. Sessions the agent wrote carry the `label` and
 * `rationale` their plan row holds; a Liftoscript-generated session has
 * neither — a script has nothing to say about why.
 */
export interface UpcomingSession {
  session: number;
  label: string | null;
  rationale: string | null;
  generated_at: string | null;
  items: UpcomingWorkout[];
}

export interface SessionTransferResponse {
  session: number;
  date: string;
  count: number;
  /** The agent-written session's label; null for a generated session. */
  label: string | null;
  message: string;
}

export interface WendlerCurrentMaxes {
  squat: number | null;
  bench: number | null;
  deadlift: number | null;
}

// Liftoscript types
export interface LiftoscriptGenerateRequest {
  script: string;
  num_cycles: number;
}

export interface LiftoscriptGenerateResponse {
  success: boolean;
  message: string;
  count: number;
  sessions: number;
  deleted_count: number;
}

/** The program the last successful generate ran — what the editor reopens on. */
export interface LiftoscriptProgram {
  script: string;
  num_cycles: number;
  /** SQLite `datetime('now')`: UTC, "YYYY-MM-DD HH:MM:SS". */
  generated_at: string;
}

export interface PresetInfo {
  name: string;
  display_name: string;
  description: string;
}

export interface PresetContent {
  name: string;
  display_name: string;
  description: string;
  script: string;
}
