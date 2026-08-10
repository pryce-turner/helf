export type Meal = "breakfast" | "lunch" | "dinner" | "snack";

export const MEALS: Meal[] = ["breakfast", "lunch", "dinner", "snack"];

/**
 * A food and the macros in one serving of it.
 *
 * `brand` is `""` and never null. SQLite treats NULLs as distinct in a UNIQUE
 * index, so the empty string is what makes `UNIQUE (name, brand)` a real
 * constraint rather than a suggestion.
 */
export interface Food {
    doc_id: number;
    name: string;
    brand: string;
    serving_desc: string | null;
    kcal_per_serving: number | null;
    protein_g: number | null;
    carb_g: number | null;
    fat_g: number | null;
    created_at: string;
}

export interface FoodCreate {
    name: string;
    brand?: string;
    serving_desc?: string | null;
    kcal_per_serving?: number | null;
    protein_g?: number | null;
    carb_g?: number | null;
    fat_g?: number | null;
}

/**
 * A logged consumption event, with the food's macros already multiplied by
 * `servings` server-side. They are computed at read time, never stored — which
 * is why correcting a food's macros corrects every past entry.
 */
export interface FoodLogEntry {
    doc_id: number;
    consumed_at: string;
    date: string;
    servings: number;
    meal: Meal | null;
    food_id: number;
    name: string;
    brand: string;
    serving_desc: string | null;
    kcal: number | null;
    protein_g: number | null;
    carb_g: number | null;
    fat_g: number | null;
}

export interface FoodLogCreate {
    food_id?: number;
    food?: FoodCreate;
    servings: number;
    meal?: Meal | null;
    consumed_at?: string;
}

/**
 * One day's totals.
 *
 * `foods_missing_macros` is not decoration. The totals coalesce unknown macros
 * to zero, so a day containing one food with no protein figure reports a
 * protein total that is simply too low. This is the count that lets the page
 * say so instead of showing a confident wrong number.
 */
export interface FoodDaySummary {
    date: string;
    kcal: number | null;
    protein_g: number | null;
    carb_g: number | null;
    fat_g: number | null;
    entries: number;
    foods_missing_macros: number;
    /**
     * The day's Katch-McArdle RMR times the activity multiplier, carried
     * forward from the last DEXA scan on or before it. Null before the first
     * scan — there is no default, and inventing one would put a target on
     * screen that no measurement supports.
     */
    kcal_target: number | null;
}
