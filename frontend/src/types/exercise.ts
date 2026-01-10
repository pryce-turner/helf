export interface Exercise {
  doc_id: number;
  name: string;
  category: string;
  last_used: string | null;
  use_count: number;
  created_at: string;
}

export interface ExerciseCreate {
  name: string;
  category: string;
}

export interface ExerciseUpdate {
  name?: string;
  category?: string;
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
