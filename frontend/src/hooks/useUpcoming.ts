import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { upcomingApi } from '@/lib/api';
import type { UpcomingWorkout, UpcomingWorkoutCreate, LiftoscriptGenerateRequest } from '@/types/upcoming';

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
    onSettled: () => {
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
    onSettled: () => {
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
    onMutate: async (session) => {
      await queryClient.cancelQueries({ queryKey: ['upcoming'] });

      const previousUpcoming = queryClient.getQueriesData<UpcomingWorkout[]>({ queryKey: ['upcoming'] });

      queryClient.setQueriesData<UpcomingWorkout[]>(
        { queryKey: ['upcoming'] },
        (old) => old?.filter((w) => w.session !== session)
      );

      return { previousUpcoming };
    },
    onError: (_err, _session, context) => {
      context?.previousUpcoming.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
    },
    onSettled: () => {
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
    onMutate: async ({ session }) => {
      await queryClient.cancelQueries({ queryKey: ['upcoming'] });
      await queryClient.cancelQueries({ queryKey: ['workouts'] });
      await queryClient.cancelQueries({ queryKey: ['calendar'] });

      const previousUpcoming = queryClient.getQueriesData<UpcomingWorkout[]>({ queryKey: ['upcoming'] });

      // Remove transferred session from upcoming cache
      queryClient.setQueriesData<UpcomingWorkout[]>(
        { queryKey: ['upcoming'] },
        (old) => old?.filter((w) => w.session !== session)
      );

      return { previousUpcoming };
    },
    onError: (_err, _vars, context) => {
      context?.previousUpcoming.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['upcoming'] });
      queryClient.invalidateQueries({ queryKey: ['workouts'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
    },
  });
}

export function useWendlerMaxes() {
  return useQuery({
    queryKey: ['wendler', 'maxes'],
    queryFn: async () => {
      const response = await upcomingApi.getWendlerMaxes();
      return response.data;
    },
  });
}

// Liftoscript hooks
export function usePresets() {
  return useQuery({
    queryKey: ['presets'],
    queryFn: async () => {
      const response = await upcomingApi.getPresets();
      return response.data;
    },
  });
}

export function usePreset(name: string) {
  return useQuery({
    queryKey: ['presets', name],
    queryFn: async () => {
      const response = await upcomingApi.getPreset(name);
      return response.data;
    },
    enabled: !!name,
  });
}

export function useLiftoscriptGenerate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: LiftoscriptGenerateRequest) => {
      const response = await upcomingApi.generateLiftoscript(request);
      return response.data;
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['upcoming'] });
      queryClient.invalidateQueries({ queryKey: ['progression'] });
    },
  });
}
