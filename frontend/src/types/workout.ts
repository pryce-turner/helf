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
  order?: number;
}

export interface CalendarResponse {
  year: number;
  month: number;
  counts: Record<string, number>;
}
