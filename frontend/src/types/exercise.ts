export interface Exercise {
  doc_id: number;
  name: string;
  category: string;
  notes: string | null;
  /** 1-5. `null` is unrated, which is not the same as a bad rating. */
  rating: number | null;
  /** Also mobility work. A flag across categories, not a category. */
  is_mobility: boolean;
  last_used: string | null;
  use_count: number;
  created_at: string;
}

export interface ExerciseCreate {
  name: string;
  category: string;
  notes?: string;
  rating?: number | null;
  is_mobility?: boolean;
}

export interface ExerciseUpdate {
  name?: string;
  category?: string;
  notes?: string;
  /** Sending `null` clears the rating; omitting the key leaves it alone. */
  rating?: number | null;
  is_mobility?: boolean;
}

export interface Category {
  doc_id: number;
  name: string;
  created_at: string;
}

export interface CategoryCreate {
  name: string;
}

export interface ExercisesByCategory {
  [category: string]: string[];
}

export interface SeedExercisesResponse {
  categories_created: number;
  exercises_created: number;
  message: string;
}
