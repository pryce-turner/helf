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
