import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { workoutsApi } from "@/lib/api";
import type { Workout, WorkoutCreate, CalendarResponse } from "@/types/workout";

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
        onMutate: async (newWorkout) => {
            await queryClient.cancelQueries({ queryKey: ["workouts"] });
            await queryClient.cancelQueries({ queryKey: ["calendar"] });

            const previousWorkouts = queryClient.getQueriesData<Workout[]>({ queryKey: ["workouts"] });
            const previousCalendar = queryClient.getQueriesData<CalendarResponse>({ queryKey: ["calendar"] });

            const optimisticWorkout: Workout = {
                doc_id: -Date.now(),
                date: newWorkout.date,
                exercise: newWorkout.exercise,
                category: newWorkout.category,
                weight: newWorkout.weight ?? null,
                weight_unit: newWorkout.weight_unit ?? "lbs",
                reps: newWorkout.reps ?? null,
                distance: newWorkout.distance ?? null,
                distance_unit: newWorkout.distance_unit ?? null,
                time: newWorkout.time ?? null,
                comment: newWorkout.comment ?? null,
                completed_at: newWorkout.completed_at ?? null,
                order: newWorkout.order ?? 0,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
            };

            queryClient.setQueriesData<Workout[]>(
                { queryKey: ["workouts"] },
                (old) => old ? [...old, optimisticWorkout] : [optimisticWorkout]
            );

            queryClient.setQueriesData<CalendarResponse>(
                { queryKey: ["calendar"] },
                (old) => {
                    if (!old) return old;
                    const day = newWorkout.date.split("-")[2];
                    const dayNum = String(parseInt(day, 10));
                    return {
                        ...old,
                        counts: { ...old.counts, [dayNum]: (old.counts[dayNum] || 0) + 1 },
                    };
                }
            );

            return { previousWorkouts, previousCalendar };
        },
        onError: (_err, _newWorkout, context) => {
            context?.previousWorkouts.forEach(([queryKey, data]) => {
                queryClient.setQueryData(queryKey, data);
            });
            context?.previousCalendar.forEach(([queryKey, data]) => {
                queryClient.setQueryData(queryKey, data);
            });
        },
        onSettled: () => {
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
        onMutate: async ({ id, workout }) => {
            await queryClient.cancelQueries({ queryKey: ["workouts"] });

            const previousWorkouts = queryClient.getQueriesData<Workout[]>({ queryKey: ["workouts"] });

            queryClient.setQueriesData<Workout[]>(
                { queryKey: ["workouts"] },
                (old) => old?.map((w) =>
                    w.doc_id === id
                        ? {
                            ...w,
                            ...workout,
                            weight: workout.weight ?? null,
                            reps: workout.reps ?? null,
                            distance: workout.distance ?? null,
                            distance_unit: workout.distance_unit ?? null,
                            time: workout.time ?? null,
                            comment: workout.comment ?? null,
                            updated_at: new Date().toISOString(),
                        }
                        : w
                )
            );

            return { previousWorkouts };
        },
        onError: (_err, _vars, context) => {
            context?.previousWorkouts.forEach(([queryKey, data]) => {
                queryClient.setQueryData(queryKey, data);
            });
        },
        onSettled: () => {
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
        onMutate: async (id) => {
            await queryClient.cancelQueries({ queryKey: ["workouts"] });
            await queryClient.cancelQueries({ queryKey: ["calendar"] });

            const previousWorkouts = queryClient.getQueriesData<Workout[]>({ queryKey: ["workouts"] });
            const previousCalendar = queryClient.getQueriesData<CalendarResponse>({ queryKey: ["calendar"] });

            // Find the workout before removing it so we can decrement calendar
            let deletedWorkout: Workout | undefined;
            for (const [, data] of previousWorkouts) {
                deletedWorkout = data?.find((w) => w.doc_id === id);
                if (deletedWorkout) break;
            }

            queryClient.setQueriesData<Workout[]>(
                { queryKey: ["workouts"] },
                (old) => old?.filter((w) => w.doc_id !== id)
            );

            if (deletedWorkout) {
                queryClient.setQueriesData<CalendarResponse>(
                    { queryKey: ["calendar"] },
                    (old) => {
                        if (!old) return old;
                        const day = deletedWorkout!.date.split("-")[2];
                        const dayNum = String(parseInt(day, 10));
                        const current = old.counts[dayNum] || 0;
                        const newCounts = { ...old.counts };
                        if (current <= 1) {
                            delete newCounts[dayNum];
                        } else {
                            newCounts[dayNum] = current - 1;
                        }
                        return { ...old, counts: newCounts };
                    }
                );
            }

            return { previousWorkouts, previousCalendar };
        },
        onError: (_err, _id, context) => {
            context?.previousWorkouts.forEach(([queryKey, data]) => {
                queryClient.setQueryData(queryKey, data);
            });
            context?.previousCalendar.forEach(([queryKey, data]) => {
                queryClient.setQueryData(queryKey, data);
            });
        },
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey: ["workouts"] });
            queryClient.invalidateQueries({ queryKey: ["calendar"] });
        },
    });
}

export function useBulkReorderWorkouts() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (workoutIds: number[]) => {
            await workoutsApi.bulkReorder(workoutIds);
        },
        onMutate: async (workoutIds) => {
            await queryClient.cancelQueries({ queryKey: ["workouts"] });

            const previousWorkouts = queryClient.getQueriesData<Workout[]>({ queryKey: ["workouts"] });

            queryClient.setQueriesData<Workout[]>(
                { queryKey: ["workouts"] },
                (old) => {
                    if (!old) return old;
                    return old.map((w) => {
                        const newOrder = workoutIds.indexOf(w.doc_id);
                        return newOrder !== -1 ? { ...w, order: newOrder } : w;
                    }).sort((a, b) => a.order - b.order);
                }
            );

            return { previousWorkouts };
        },
        onError: (_err, _ids, context) => {
            context?.previousWorkouts.forEach(([queryKey, data]) => {
                queryClient.setQueryData(queryKey, data);
            });
        },
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey: ["workouts"] });
        },
    });
}

export function useToggleComplete() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            id,
            completed,
        }: {
            id: number;
            completed: boolean;
        }) => {
            const response = await workoutsApi.toggleComplete(id, completed);
            return response.data;
        },
        onMutate: async ({ id, completed }) => {
            await queryClient.cancelQueries({ queryKey: ["workouts"] });

            const previousWorkouts = queryClient.getQueriesData<Workout[]>({ queryKey: ["workouts"] });

            queryClient.setQueriesData<Workout[]>(
                { queryKey: ["workouts"] },
                (old) => old?.map((w) =>
                    w.doc_id === id
                        ? { ...w, completed_at: completed ? new Date().toISOString() : null }
                        : w
                )
            );

            return { previousWorkouts };
        },
        onError: (_err, _vars, context) => {
            context?.previousWorkouts.forEach(([queryKey, data]) => {
                queryClient.setQueryData(queryKey, data);
            });
        },
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey: ["workouts"] });
        },
    });
}

export function useMoveToDate() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            sourceDate,
            targetDate,
        }: {
            sourceDate: string;
            targetDate: string;
        }) => {
            const response = await workoutsApi.moveToDate(sourceDate, targetDate);
            return response.data;
        },
        onMutate: async ({ sourceDate, targetDate }) => {
            await queryClient.cancelQueries({ queryKey: ["workouts"] });
            await queryClient.cancelQueries({ queryKey: ["calendar"] });

            const previousWorkouts = queryClient.getQueriesData<Workout[]>({ queryKey: ["workouts"] });
            const previousCalendar = queryClient.getQueriesData<CalendarResponse>({ queryKey: ["calendar"] });

            // Count workouts being moved from the source date cache
            let movedCount = 0;

            queryClient.setQueriesData<Workout[]>(
                { queryKey: ["workouts"] },
                (old) => {
                    if (!old) return old;
                    const remaining = old.filter((w) => w.date !== sourceDate);
                    movedCount = old.length - remaining.length;
                    return remaining;
                }
            );

            // Update calendar counts
            if (movedCount > 0) {
                queryClient.setQueriesData<CalendarResponse>(
                    { queryKey: ["calendar"] },
                    (old) => {
                        if (!old) return old;
                        const sourceDay = String(parseInt(sourceDate.split("-")[2], 10));
                        const targetDay = String(parseInt(targetDate.split("-")[2], 10));
                        const newCounts = { ...old.counts };
                        delete newCounts[sourceDay];
                        newCounts[targetDay] = (newCounts[targetDay] || 0) + movedCount;
                        return { ...old, counts: newCounts };
                    }
                );
            }

            return { previousWorkouts, previousCalendar };
        },
        onError: (_err, _vars, context) => {
            context?.previousWorkouts.forEach(([queryKey, data]) => {
                queryClient.setQueryData(queryKey, data);
            });
            context?.previousCalendar.forEach(([queryKey, data]) => {
                queryClient.setQueryData(queryKey, data);
            });
        },
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey: ["workouts"] });
            queryClient.invalidateQueries({ queryKey: ["calendar"] });
        },
    });
}

export function useCopyToDate() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            sourceDate,
            targetDate,
        }: {
            sourceDate: string;
            targetDate: string;
        }) => {
            const response = await workoutsApi.copyToDate(sourceDate, targetDate);
            return response.data;
        },
        onMutate: async () => {
            // Can't predict new IDs from server, just cancel queries to avoid races
            await queryClient.cancelQueries({ queryKey: ["workouts"] });
            await queryClient.cancelQueries({ queryKey: ["calendar"] });
        },
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey: ["workouts"] });
            queryClient.invalidateQueries({ queryKey: ["calendar"] });
        },
    });
}
