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
   * The unit a cardio exercise is measured in. Non-null *is* what makes it
   * cardio — there is no separate flag. Only the default a new set starts
   * with; each set keeps its own `amount_unit`.
   */
  cardio_unit: string | null;
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
  cardio_unit?: string | null;
}

export interface ExerciseUpdate {
  name?: string;
  category?: string;
  form?: string;
  application?: string;
  /** Sending `null` clears the rating; omitting the key leaves it alone. */
  rating?: number | null;
  /** Sending `null` makes it resistance work again; omitting leaves it. */
  cardio_unit?: string | null;
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
