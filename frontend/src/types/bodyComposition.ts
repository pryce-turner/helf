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
  /**
   * Kilograms, unlike its neighbours — the unit is in the name because
   * `metric_def` defines bone as kg for DEXA and openScale reports kg. See
   * docs/plans/0010-retire-body-composition.md §2.
   */
  bone_mass_kg: number | null;
  visceral_fat: number | null;
  metabolic_age: number | null;
  protein_pct: number | null;
  created_at: string;
  /** Which instrument produced this - 'openscale', 'bodyspec' or 'manual'.
   *  A bioimpedance estimate and a DEXA measurement are not interchangeable. */
  source: string;
}

export interface BodyCompositionStats {
  total_measurements: number;
  latest_weight: number | null;
  latest_body_fat: number | null;
  latest_muscle_mass: number | null;
  /** Source of the most recent measurement the latest_* figures come from. */
  latest_source: string | null;
  weight_change: number | null;
  body_fat_change: number | null;
  muscle_mass_change: number | null;
  /** The single series the *_change figures describe. Deltas are never
   *  computed across instruments - that would report the gap between them
   *  as a change in the body. */
  primary_source: string | null;
  first_date: string | null;
  latest_date: string | null;
}

export interface BodyCompositionTrend {
  dates: string[];
  weights: (number | null)[];
  body_fat_pcts: (number | null)[];
  muscle_masses: (number | null)[];
  water_pcts: (number | null)[];
  /** Runs parallel to `dates`. Without it a chart joins a quarterly DEXA
   *  point to a daily scale reading with a line, asserting a trajectory
   *  across three months that nothing measured. */
  sources: string[];
}

export interface BodySpecSyncResult {
  scans_found: number;
  imported: number;
  skipped: number;
  metrics_written: number;
}

/**
 * What one scale drain did — plan 0015 §4.
 *
 * `skipped` is the number already held. Unlike the BodySpec sync, a high
 * `skipped` is the *normal* result here: the scale replays all thirty stored
 * weighings on every connect, so most of any drain is already in the database.
 */
export interface ScaleSyncResult {
    readings_received: number;
    imported: number;
    skipped: number;
}
