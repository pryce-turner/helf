export interface UpcomingWorkout {
  doc_id: number;
  session: number;
  exercise: string;
  category: string;
  weight: number | null;
  weight_unit: string;
  reps: number | null;
  distance: number | null;
  distance_unit: string | null;
  time: string | null;
  comment: string | null;
  created_at: string;
}

export interface UpcomingWorkoutCreate {
  session: number;
  exercise: string;
  category: string;
  weight?: number | null;
  weight_unit?: string;
  reps?: number | null;
  distance?: number | null;
  distance_unit?: string | null;
  time?: string | null;
  comment?: string | null;
}

export interface WendlerCurrentMaxes {
  squat: number | null;
  bench: number | null;
  deadlift: number | null;
}

// Liftoscript types
export interface LiftoscriptGenerateRequest {
  script: string;
  squat_max?: number | null;
  bench_max?: number | null;
  deadlift_max?: number | null;
  num_cycles: number;
}

export interface LiftoscriptGenerateResponse {
  success: boolean;
  message: string;
  count: number;
  sessions: number;
  deleted_count: number;
}

export interface PresetInfo {
  name: string;
  display_name: string;
  description: string;
  requires_maxes: boolean;
}

export interface PresetContent {
  name: string;
  display_name: string;
  script: string;
}
