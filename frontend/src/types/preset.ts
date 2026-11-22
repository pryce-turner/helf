/**
 * A hand-built workout, applied to a day as planned sets (plan 0020).
 *
 * Not the Liftoscript presets in `upcoming.ts` (`PresetInfo`), which are
 * program templates that generate the upcoming queue.
 */
export interface PresetItem {
  doc_id: number;
  preset_id: number;
  order: number;
  exercise: string;
  category: string;
  weight: number | null;
  weight_unit: string;
  reps: number | null;
  distance: number | null;
  distance_unit: string | null;
  comment: string | null;
  is_mobility: boolean;
  work_seconds: number | null;
  rest_seconds: number | null;
  rest_after_seconds: number | null;
}

export interface WorkoutPreset {
  doc_id: number;
  name: string;
  created_at: string;
  updated_at: string;
  items: PresetItem[];
}

/** A tile's targets, as the day editor's forms produce them — no date. */
export interface PresetItemCreate {
  exercise: string;
  category: string;
  weight?: number | null;
  weight_unit?: string;
  reps?: number | null;
  distance?: number | null;
  distance_unit?: string | null;
  comment?: string | null;
  is_mobility?: boolean;
  work_seconds?: number | null;
  rest_seconds?: number | null;
  rest_after_seconds?: number | null;
  order?: number | null;
}

export interface PresetApplyResponse {
  preset_id: number;
  date: string;
  count: number;
  message: string;
}
