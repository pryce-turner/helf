export interface BodyComposition {
  doc_id: number;
  timestamp: string;
  date: string;
  weight: number;
  weight_unit: string;
  body_fat_pct: number | null;
  muscle_mass: number | null;
  bmi: number | null;
  water_pct: number | null;
  bone_mass: number | null;
  visceral_fat: number | null;
  metabolic_age: number | null;
  protein_pct: number | null;
  created_at: string;
}

export interface BodyCompositionStats {
  total_measurements: number;
  latest_weight: number | null;
  latest_body_fat: number | null;
  latest_muscle_mass: number | null;
  weight_change: number | null;
  body_fat_change: number | null;
  muscle_mass_change: number | null;
  first_date: string | null;
  latest_date: string | null;
}

export interface BodyCompositionTrend {
  dates: string[];
  weights: (number | null)[];
  body_fat_pcts: (number | null)[];
  muscle_masses: (number | null)[];
  water_pcts: (number | null)[];
}
