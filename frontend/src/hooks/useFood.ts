import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { foodApi } from "@/lib/api";
import type { FoodCreate, FoodLogCreate } from "@/types/food";

/**
 * One day's totals and entries.
 *
 * `staleTime: 0` overrides the app-wide five minutes. Food logging is a
 * several-times-a-day loop, often from two devices, and a five-minute-old
 * calorie total is worse than no total — it silently under-reports whatever
 * was logged from the other phone.
 */
export function useFoodDay(date: string) {
    return useQuery({
        queryKey: ["food", "day", date],
        queryFn: async () => (await foodApi.getDay(date)).data,
        staleTime: 0,
    });
}

export function useFoodSummary(start: string, end: string) {
    return useQuery({
        queryKey: ["food", "summary", start, end],
        queryFn: async () => (await foodApi.getSummary(start, end)).data,
    });
}

/**
 * Catalog search, for the "have I logged this before?" typeahead.
 *
 * Disabled below two characters: a one-letter query matches most of the
 * catalog and the result is noise, not a shortlist.
 */
export function useFoodSearch(q: string, kind?: string) {
    return useQuery({
        queryKey: ["food", "search", q, kind],
        queryFn: async () => (await foodApi.search(q, 50, kind)).data,
        enabled: q.trim().length >= 2,
        staleTime: 60 * 1000,
    });
}

/**
 * What an edit would rewrite. Fetched when the editor opens, not with the
 * catalog list — it is one query per food and only matters once.
 */
export function useFoodUsage(id: number | null) {
    return useQuery({
        queryKey: ["food", "usage", id],
        queryFn: async () => (await foodApi.usage(id!)).data,
        enabled: id != null,
        staleTime: 0,
    });
}

/**
 * The whole supplement catalog, including entries no group uses.
 *
 * Separate from `useFoodSearch`, which is a typeahead and stays disabled below
 * two characters — this one always returns everything.
 */
export function useSupplementCatalog() {
    return useQuery({
        queryKey: ["food", "catalog", "supplement"],
        queryFn: async () => (await foodApi.search(undefined, 500, "supplement")).data,
    });
}

/**
 * The supplement log, newest first across days.
 *
 * Under the `["food"]` key namespace on purpose: logging a stack, deleting an
 * entry and editing a supplement all invalidate `["food"]` already, so this
 * list refreshes with everything else that changes it.
 */
export function useSupplementLog(limit: number = 50) {
    return useQuery({
        queryKey: ["food", "log", "recent", "supplement", limit],
        queryFn: async () => (await foodApi.getRecentLog("supplement", limit)).data,
        staleTime: 0,
    });
}

export function useLogFood() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (entry: FoodLogCreate) =>
            (await foodApi.log(entry)).data,
        // No optimistic update, deliberately. The macros on an entry are
        // resolved server-side from the food row, so an optimistic entry for a
        // food the client has not seen would have to guess its calories — and
        // a guessed number in a calorie total is the one thing this page must
        // not do.
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["food"] });
        },
    });
}

export function useDeleteFoodLog() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await foodApi.deleteLog(id);
            return id;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["food"] });
            // `taken_today` is derived from exactly these rows, so deleting
            // one can flip a group back to untaken. Cheap, and wrong the other
            // way: a stale badge is how you take a stack twice.
            queryClient.invalidateQueries({ queryKey: ["stacks"] });
        },
    });
}

export function useUpdateFood() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({
            id,
            changes,
        }: {
            id: number;
            changes: Partial<FoodCreate>;
        }) => (await foodApi.update(id, changes)).data,
        onSuccess: () => {
            // Every day that ever used this food changed too, so the whole
            // namespace goes rather than one date.
            queryClient.invalidateQueries({ queryKey: ["food"] });
        },
    });
}
