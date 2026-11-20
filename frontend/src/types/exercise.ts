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
   * In the movement break pool. A fact about the movement's setup — it needs
   * no equipment — not a judgement that it is mobility work.
   */
  movement_break_enabled: boolean;
  /**
   * Field configuration (plan 0018): which groups a new set tile for this
   * movement offers, and what each offers as a default. Enabled with a null
   * default means "offer the input, leave it blank"; disabled groups keep
   * their defaults stored, so re-enabling does not erase them.
   */
  reps_enabled: boolean;
  default_reps: number | null;
  weight_enabled: boolean;
  /** Total pounds — for a Farmer Carry, across both hands, not per hand. */
  default_weight_lb: number | null;
  distance_enabled: boolean;
  default_distance: number | null;
  default_distance_unit: string | null;
  time_enabled: boolean;
  default_work_seconds: number | null;
  default_rest_seconds: number | null;
  default_rest_after_seconds: number | null;
  /** Set only by performed work — a suggestion never moves it (plan 0018). */
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
  movement_break_enabled?: boolean;
  reps_enabled?: boolean;
  default_reps?: number | null;
  weight_enabled?: boolean;
  default_weight_lb?: number | null;
  distance_enabled?: boolean;
  default_distance?: number | null;
  default_distance_unit?: string | null;
  time_enabled?: boolean;
  default_work_seconds?: number | null;
  default_rest_seconds?: number | null;
  default_rest_after_seconds?: number | null;
}

export interface ExerciseUpdate {
  name?: string;
  category?: string;
  form?: string;
  application?: string;
  /** Sending `null` clears the rating; omitting the key leaves it alone. */
  rating?: number | null;
  movement_break_enabled?: boolean;
  reps_enabled?: boolean;
  /** Sending `null` clears the default; omitting the key leaves it alone. */
  default_reps?: number | null;
  weight_enabled?: boolean;
  default_weight_lb?: number | null;
  distance_enabled?: boolean;
  default_distance?: number | null;
  default_distance_unit?: string | null;
  time_enabled?: boolean;
  default_work_seconds?: number | null;
  default_rest_seconds?: number | null;
  default_rest_after_seconds?: number | null;
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
