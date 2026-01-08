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

export interface WendlerGenerateRequest {
  num_cycles?: number;
  squat_max?: number | null;
  bench_max?: number | null;
  deadlift_max?: number | null;
}

export interface WendlerGenerateResponse {
  success: boolean;
  message: string;
  count: number;
  sessions?: number;
  session_range?: number[];
  cycles?: number;
}

export interface WendlerCurrentMaxes {
  squat: number | null;
  bench: number | null;
  deadlift: number | null;
}
