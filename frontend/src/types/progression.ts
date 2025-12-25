export interface ProgressionDataPoint {
  date: string;
  weight: number;
  weight_unit: string;
  reps: number | string;
  estimated_1rm: number;
  comment: string | null;
}

export interface UpcomingProgressionDataPoint {
  session: number;
  projected_date: string;
  weight: number;
  weight_unit: string;
  reps: number | string;
  estimated_1rm: number;
  comment: string | null;
}

export interface ProgressionResponse {
  exercise: string;
  historical: ProgressionDataPoint[];
  upcoming: UpcomingProgressionDataPoint[];
}
