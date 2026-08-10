import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { stacksApi } from "@/lib/api";
import type { StackCreate, StackUpdate } from "@/types/stack";

/**
 * All stacks, with `taken_today` per stack.
 *
 * `staleTime: 0` for the same reason as `useFoodDay` — this is a
 * several-times-a-day loop, often from two devices, and a cached "not taken
 * yet" is how you end up taking your morning stack twice.
 */
export function useStacks() {
    return useQuery({
        queryKey: ["stacks"],
        queryFn: async () => (await stacksApi.getAll()).data,
        staleTime: 0,
    });
}

/**
 * Logging a stack writes `food_log` rows, so the food day has to be
 * invalidated alongside the stacks themselves — `taken_today` is derived from
 * exactly those rows.
 */
function invalidateBoth(queryClient: ReturnType<typeof useQueryClient>) {
    queryClient.invalidateQueries({ queryKey: ["stacks"] });
    queryClient.invalidateQueries({ queryKey: ["food"] });
}

export function useLogStack() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => (await stacksApi.log(id)).data,
        onSuccess: () => invalidateBoth(queryClient),
    });
}

export function useCreateStack() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (stack: StackCreate) =>
            (await stacksApi.create(stack)).data,
        onSuccess: () => invalidateBoth(queryClient),
    });
}

export function useUpdateStack() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, changes }: { id: number; changes: StackUpdate }) =>
            (await stacksApi.update(id, changes)).data,
        onSuccess: () => invalidateBoth(queryClient),
    });
}

export function useDeleteStack() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: number) => {
            await stacksApi.delete(id);
            return id;
        },
        onSuccess: () => invalidateBoth(queryClient),
    });
}
