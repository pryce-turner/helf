import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { workoutsApi } from "@/lib/api";
import type { WorkoutCreate } from "@/types/workout";

export function useWorkouts(params?: {
    date?: string;
    skip?: number;
    limit?: number;
}) {
    return useQuery({
        queryKey: ["workouts", params],
        queryFn: async () => {
            const response = await workoutsApi.getAll(params);
            return response.data;
        },
    });
}

export function useWorkout(id: number) {
    return useQuery({
        queryKey: ["workouts", id],
        queryFn: async () => {
            const response = await workoutsApi.getById(id);
            return response.data;
        },
        enabled: !!id,
    });
}

export function useCalendar(year: number, month: number) {
    return useQuery({
        queryKey: ["calendar", year, month],
        queryFn: async () => {
            const response = await workoutsApi.getCalendar(year, month);
            return response.data;
        },
    });
}

export function useCreateWorkout() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (workout: WorkoutCreate) => {
            const response = await workoutsApi.create(workout);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["workouts"] });
            queryClient.invalidateQueries({ queryKey: ["calendar"] });
        },
    });
}

export function useUpdateWorkout() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            id,
            workout,
        }: {
            id: number;
            workout: WorkoutCreate;
        }) => {
            const response = await workoutsApi.update(id, workout);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["workouts"] });
            queryClient.invalidateQueries({ queryKey: ["calendar"] });
        },
    });
}

export function useDeleteWorkout() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: number) => {
            await workoutsApi.delete(id);
            return id;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["workouts"] });
            queryClient.invalidateQueries({ queryKey: ["calendar"] });
        },
    });
}

export function useReorderWorkout() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            id,
            direction,
        }: {
            id: number;
            direction: "up" | "down";
        }) => {
            await workoutsApi.reorder(id, direction);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["workouts"] });
        },
    });
}
