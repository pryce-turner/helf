import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { presetsApi } from "@/lib/api";
import type { PresetItemCreate, WorkoutPreset } from "@/types/preset";

/**
 * Hand-built presets (plan 0020). Named `useWorkoutPreset*` because
 * `usePresets` in useUpcoming is the Liftoscript template list.
 */
const KEY = ["workout-presets"] as const;

export function useWorkoutPresets() {
    return useQuery({
        queryKey: KEY,
        queryFn: async () => (await presetsApi.getAll()).data,
    });
}

export function useWorkoutPreset(id: number | undefined) {
    return useQuery({
        queryKey: [...KEY, id],
        queryFn: async () => (await presetsApi.getById(id!)).data,
        enabled: id != null && !Number.isNaN(id),
    });
}

function useInvalidate() {
    const queryClient = useQueryClient();
    return () => queryClient.invalidateQueries({ queryKey: KEY });
}

export function useCreateWorkoutPreset() {
    const invalidate = useInvalidate();
    return useMutation({
        mutationFn: async (name?: string) => (await presetsApi.create(name)).data,
        onSettled: invalidate,
    });
}

export function useRenameWorkoutPreset() {
    const invalidate = useInvalidate();
    return useMutation({
        mutationFn: async ({ id, name }: { id: number; name: string }) =>
            (await presetsApi.rename(id, name)).data,
        onSettled: invalidate,
    });
}

export function useDeleteWorkoutPreset() {
    const invalidate = useInvalidate();
    return useMutation({
        mutationFn: async (id: number) => {
            await presetsApi.delete(id);
            return id;
        },
        onSettled: invalidate,
    });
}

export function useAddPresetItem(presetId: number) {
    const invalidate = useInvalidate();
    return useMutation({
        mutationFn: async (item: PresetItemCreate) =>
            (await presetsApi.addItem(presetId, item)).data,
        onSettled: invalidate,
    });
}

export function useUpdatePresetItem() {
    const invalidate = useInvalidate();
    return useMutation({
        mutationFn: async ({ id, item }: { id: number; item: PresetItemCreate }) =>
            (await presetsApi.updateItem(id, item)).data,
        onSettled: invalidate,
    });
}

export function useDeletePresetItem() {
    const invalidate = useInvalidate();
    return useMutation({
        mutationFn: async (id: number) => {
            await presetsApi.deleteItem(id);
            return id;
        },
        onSettled: invalidate,
    });
}

/** Optimistic, like the day's: a dragged tile must not snap back while the
 *  write is in flight. */
export function useReorderPresetItems(presetId: number) {
    const queryClient = useQueryClient();
    const key = [...KEY, presetId];
    return useMutation({
        mutationFn: async (itemIds: number[]) => {
            await presetsApi.reorder(presetId, itemIds);
        },
        onMutate: async (itemIds) => {
            await queryClient.cancelQueries({ queryKey: key });
            const previous = queryClient.getQueryData<WorkoutPreset>(key);
            if (previous) {
                const position = new Map(itemIds.map((id, i) => [id, i + 1]));
                queryClient.setQueryData<WorkoutPreset>(key, {
                    ...previous,
                    items: previous.items.map((item) => ({
                        ...item,
                        order: position.get(item.doc_id) ?? item.order,
                    })),
                });
            }
            return { previous };
        },
        onError: (_err, _ids, context) => {
            if (context?.previous) queryClient.setQueryData(key, context.previous);
        },
        onSettled: () => queryClient.invalidateQueries({ queryKey: KEY }),
    });
}

export function useApplyWorkoutPreset() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, date }: { id: number; date: string }) =>
            (await presetsApi.apply(id, date)).data,
        onSettled: () => {
            // The day it landed on, and the calendar's view of it.
            queryClient.invalidateQueries({ queryKey: ["workouts"] });
            queryClient.invalidateQueries({ queryKey: ["calendar"] });
        },
    });
}
