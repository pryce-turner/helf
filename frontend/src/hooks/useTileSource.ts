import { createContext, useCallback, useContext, useMemo } from "react";
import {
    useWorkouts,
    useCreateWorkout,
    useUpdateWorkout,
    useDeleteWorkout,
    useBulkReorderWorkouts,
} from "@/hooks/useWorkouts";
import {
    useWorkoutPreset,
    useAddPresetItem,
    useUpdatePresetItem,
    useDeletePresetItem,
    useReorderPresetItems,
} from "@/hooks/useWorkoutPresets";
import type { Workout, WorkoutCreate } from "@/types/workout";
import type { PresetItem, PresetItemCreate, WorkoutPreset } from "@/types/preset";

/**
 * Where the day editor's tiles come from and go to (plan 0020).
 *
 * The editor — cards, add form, inline edit, drag reorder, delete — is the
 * same whether it edits a dated day or a preset. What differs is the store,
 * so that is all this abstracts: a day reads and writes `workouts`, a preset
 * its own items. Preset items are handed over in the `Workout` shape as
 * planned tiles (no completion, no actuals), so a card cannot tell them apart.
 *
 * Every function here is stable across renders: the cards are memoised on
 * their callbacks, and a new function per render would re-render the list.
 */
export interface TileSource {
    kind: "day" | "preset";
    tiles: Workout[] | undefined;
    isLoading: boolean;
    create: (tile: WorkoutCreate) => Promise<unknown>;
    update: (id: number, tile: WorkoutCreate) => void;
    updateAsync: (id: number, tile: WorkoutCreate) => Promise<unknown>;
    remove: (id: number) => Promise<unknown>;
    reorder: (ids: number[]) => void;
}

export function useDayTileSource(date: string | undefined): TileSource {
    const { data, isLoading } = useWorkouts({ date });
    const { mutateAsync: createAsync } = useCreateWorkout();
    const { mutate: updateMutate, mutateAsync: updateMutateAsync } = useUpdateWorkout();
    const { mutateAsync: removeAsync } = useDeleteWorkout();
    const { mutate: reorderMutate } = useBulkReorderWorkouts();

    const update = useCallback(
        (id: number, workout: WorkoutCreate) => updateMutate({ id, workout }),
        [updateMutate],
    );
    const updateAsync = useCallback(
        (id: number, workout: WorkoutCreate) => updateMutateAsync({ id, workout }),
        [updateMutateAsync],
    );

    return useMemo(
        () => ({
            kind: "day" as const,
            tiles: data,
            isLoading,
            create: createAsync,
            update,
            updateAsync,
            remove: removeAsync,
            reorder: reorderMutate,
        }),
        [data, isLoading, createAsync, update, updateAsync, removeAsync, reorderMutate],
    );
}

/** A preset item as a planned tile, which is all it is. */
export function presetItemToTile(item: PresetItem, preset: WorkoutPreset): Workout {
    return {
        doc_id: item.doc_id,
        date: "",
        exercise: item.exercise,
        category: item.category,
        weight: item.weight,
        weight_unit: item.weight_unit,
        reps: item.reps,
        distance: item.distance,
        distance_unit: item.distance_unit,
        time: null,
        comment: item.comment,
        completed_at: null,
        is_mobility: item.is_mobility,
        order: item.order,
        created_at: preset.created_at,
        updated_at: preset.updated_at,
        work_seconds: item.work_seconds,
        rest_seconds: item.rest_seconds,
        rest_after_seconds: item.rest_after_seconds,
        completed_reps: null,
        actual_work_seconds: null,
        actual_rest_seconds: null,
        actual_rest_after_seconds: null,
        ended_early: false,
    };
}

/** The targets of a day-editor form, without the day. */
function toPresetItem(tile: WorkoutCreate): PresetItemCreate {
    return {
        exercise: tile.exercise,
        category: tile.category,
        weight: tile.weight ?? null,
        weight_unit: tile.weight_unit,
        reps: tile.reps ?? null,
        distance: tile.distance ?? null,
        distance_unit: tile.distance_unit ?? null,
        comment: tile.comment ?? null,
        is_mobility: tile.is_mobility ?? false,
        work_seconds: tile.work_seconds ?? null,
        rest_seconds: tile.rest_seconds ?? null,
        rest_after_seconds: tile.rest_after_seconds ?? null,
        order: tile.order ?? null,
    };
}

export function usePresetTileSource(presetId: number): TileSource {
    const { data: preset, isLoading } = useWorkoutPreset(presetId);
    const { mutateAsync: addAsync } = useAddPresetItem(presetId);
    const { mutate: updateMutate, mutateAsync: updateMutateAsync } = useUpdatePresetItem();
    const { mutateAsync: removeAsync } = useDeletePresetItem();
    const { mutate: reorderMutate } = useReorderPresetItems(presetId);

    const tiles = useMemo(
        () => preset?.items.map((item) => presetItemToTile(item, preset)),
        [preset],
    );
    const create = useCallback(
        (tile: WorkoutCreate) => addAsync(toPresetItem(tile)),
        [addAsync],
    );
    const update = useCallback(
        (id: number, tile: WorkoutCreate) => updateMutate({ id, item: toPresetItem(tile) }),
        [updateMutate],
    );
    const updateAsync = useCallback(
        (id: number, tile: WorkoutCreate) =>
            updateMutateAsync({ id, item: toPresetItem(tile) }),
        [updateMutateAsync],
    );

    return useMemo(
        () => ({
            kind: "preset" as const,
            tiles,
            isLoading,
            create,
            update,
            updateAsync,
            remove: removeAsync,
            reorder: reorderMutate,
        }),
        [tiles, isLoading, create, update, updateAsync, removeAsync, reorderMutate],
    );
}

/** For the pieces of the editor that write without being handed a callback —
 *  the inline edit form's Save and Duplicate. */
export const TileSourceContext = createContext<TileSource | null>(null);

export function useTileSourceContext(): TileSource {
    const source = useContext(TileSourceContext);
    if (!source) throw new Error("TileSourceContext missing: render inside a DayEditor");
    return source;
}
