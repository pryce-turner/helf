import type { FoodCreate, FoodLogEntry, FoodKind } from "./food";

/**
 * One consumable in a stack.
 *
 * `servings` lives on the membership, not on the food: two omega capsules in
 * the morning and one in the evening is the same product taken differently.
 */
export interface StackItem {
    doc_id: number;
    food_id: number;
    name: string;
    brand: string;
    kind: FoodKind;
    /** Free text, e.g. "1 softgel, 1000mg EPA". Rendered beside `servings`. */
    serving_desc: string | null;
    servings: number;
    order: number;
    kcal_per_serving: number | null;
}

export interface StackItemCreate {
    food_id?: number;
    food?: FoodCreate;
    servings: number;
}

/**
 * A named group of consumables, logged in one action.
 *
 * `taken_today` is computed from `food_log` — every one of the stack's foods
 * appears in today's entries — not from a marker the log button writes. So it
 * is true whether the stack was tapped or the items entered by hand, and
 * editing a stack cannot rewrite what a past day claims.
 */
export interface Stack {
    doc_id: number;
    name: string;
    note: string | null;
    order: number;
    created_at: string;
    items: StackItem[];
    taken_today: boolean;
    last_taken: string | null;
}

export interface StackCreate {
    name: string;
    note?: string | null;
    items: StackItemCreate[];
}

export interface StackUpdate {
    name?: string;
    note?: string | null;
    order?: number;
    items?: StackItemCreate[];
}

export interface StackLogResult {
    stack: string;
    consumed_at: string;
    entries: FoodLogEntry[];
}
