export interface Workout {
  id: number;
  date: string;
  exercise: string;
  category: string;
  weight: number | null;
  weight_unit: string;
  reps: number | string | null;
  distance: number | null;
  distance_unit: string | null;
  time: string | null;
  comment: string | null;
  order: number;
  created_at: string;
  updated_at: string;
}

export interface WorkoutCreate {
  date: string;
  exercise: string;
  category: string;
  weight?: number | null;
  weight_unit?: string;
  reps?: number | string | null;
  distance?: number | null;
  distance_unit?: string | null;
  time?: string | null;
  comment?: string | null;
  order?: number;
}

export interface CalendarResponse {
  year: number;
  month: number;
  counts: Record<string, number>;
}
