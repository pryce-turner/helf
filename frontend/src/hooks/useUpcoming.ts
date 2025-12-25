import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { upcomingApi } from '@/lib/api';
import type { UpcomingWorkoutCreate } from '@/types/upcoming';

export function useUpcomingWorkouts() {
  return useQuery({
    queryKey: ['upcoming'],
    queryFn: async () => {
      const response = await upcomingApi.getAll();
      return response.data;
    },
  });
}

export function useUpcomingSession(session: number) {
  return useQuery({
    queryKey: ['upcoming', 'session', session],
    queryFn: async () => {
      const response = await upcomingApi.getSession(session);
      return response.data;
    },
    enabled: session > 0,
  });
}

export function useCreateUpcomingWorkout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (workout: UpcomingWorkoutCreate) => {
      const response = await upcomingApi.create(workout);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['upcoming'] });
    },
  });
}

export function useCreateBulkUpcoming() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (workouts: UpcomingWorkoutCreate[]) => {
      const response = await upcomingApi.createBulk(workouts);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['upcoming'] });
    },
  });
}

export function useDeleteUpcomingSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (session: number) => {
      await upcomingApi.deleteSession(session);
      return session;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['upcoming'] });
    },
  });
}

export function useTransferSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ session, date }: { session: number; date: string }) => {
      const response = await upcomingApi.transferSession(session, date);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['upcoming'] });
      queryClient.invalidateQueries({ queryKey: ['workouts'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
    },
  });
}
