export interface Exercise {
  doc_id: number;
  name: string;
  category: string;
  /** How to perform it. Reference material, rarely edited. */
  form: string | null;
  /** symptom -> likely cause -> what to change. What the loop learns. */
  application: string | null;
  /** 1-5. `null` is unrated, which is not the same as a bad rating. */
  rating: number | null;
  /**
   * In the movement break pool, and how long one bout of it lasts. `null` is
   * "not in the pool" — a fact about the movement's setup, not a judgement
   * that it is mobility work.
   */
  movement_break_seconds: number | null;
  /** Also mobility work. A flag across categories, not a category. */
  last_used: string | null;
  use_count: number;
  created_at: string;
}

export interface ExerciseCreate {
  name: string;
  category: string;
  form?: string;
  application?: string;
  rating?: number | null;
  movement_break_seconds?: number | null;
}

export interface ExerciseUpdate {
  name?: string;
  category?: string;
  form?: string;
  application?: string;
  /** Sending `null` clears the rating; omitting the key leaves it alone. */
  rating?: number | null;
  /** Sending `null` removes it from the movement break pool; omitting leaves it. */
  movement_break_seconds?: number | null;
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
