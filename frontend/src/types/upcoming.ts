export interface UpcomingWorkout {
  id: number;
  session: number;
  exercise: string;
  category: string;
  weight: number | null;
  weight_unit: string;
  reps: number | string | null;
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
  reps?: number | string | null;
  distance?: number | null;
  distance_unit?: string | null;
  time?: string | null;
  comment?: string | null;
}
