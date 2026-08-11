export interface ProgressionSet {
  weight: number;
  weight_unit: string;
  reps: number;
  estimated_1rm: number;
  comment: string | null;
}

/**
 * A day's work on one exercise. The top-level numbers are the day's best set
 * by estimated 1RM — the single point the chart plots — and `sets` carries the
 * whole session underneath, in the order performed.
 */
export interface ProgressionDataPoint {
  date: string;
  weight: number;
  weight_unit: string;
  reps: number;
  estimated_1rm: number;
  comment: string | null;
  sets: ProgressionSet[];
}

export interface UpcomingProgressionDataPoint {
  session: number;
  projected_date: string;
  weight: number;
  weight_unit: string;
  reps: number;
  estimated_1rm: number;
  comment: string | null;
}

export interface ProgressionResponse {
  exercise: string;
  historical: ProgressionDataPoint[];
  upcoming: UpcomingProgressionDataPoint[];
}
