export type Meal = "breakfast" | "lunch" | "dinner" | "snack";

/**
 * A supplement is a `food` row too — a thing with a serving size that you
 * swallow at a time. `kind` is what keeps a vitamin out of the meal list and
 * out of the missing-macros warning. See docs/plans/0011-supplement-stacks.md.
 */
export type FoodKind = "food" | "supplement";

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
    kind: FoodKind;
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
    kind?: FoodKind;
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
    kind: FoodKind;
    serving_desc: string | null;
    kcal: number | null;
    protein_g: number | null;
    carb_g: number | null;
    fat_g: number | null;
}

/**
 * What an edit to a food would reach.
 *
 * Read before showing an edit form. Macros are derived at read time, so a
 * correction rewrites every past entry's totals — intended, and worth stating
 * the size of beforehand rather than leaving to be discovered.
 */
export interface FoodUsage {
    food_id: number;
    entries: number;
    first_logged: string | null;
    last_logged: string | null;
    /** Named, so you can see which groups you are about to change. */
    stacks: string[];
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
    /** Count of supplement doses logged, not one column per supplement. */
    supplements_taken: number;
    /**
     * The day's Katch-McArdle RMR times the activity multiplier, carried
     * forward from the last DEXA scan on or before it. Null before the first
     * scan — there is no default, and inventing one would put a target on
     * screen that no measurement supports.
     */
    kcal_target: number | null;
}
