import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { mobilityApi } from '../lib/api';
import type { MovementBreakLog } from '../types/mobility';

export function useMobilityPending() {
  return useQuery({
    queryKey: ['mobility', 'pending'],
    queryFn: async () => {
      const response = await mobilityApi.getPending();
      return response.data;
    },
  });
}

export function useTransferMobility() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ date, session }: { date: string; session: number }) => {
      const response = await mobilityApi.transfer(date, session);
      return response.data;
    },
    // No optimistic update, deliberately. Transferring writes rows the user is
    // about to go and log against, and showing the empty state before the
    // server has confirmed would invite a second tap and a duplicated session.
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mobility'] });
      queryClient.invalidateQueries({ queryKey: ['workouts'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
    },
  });
}

export function useClearMobilityPending() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (session: number) => {
      await mobilityApi.clearPending(session);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mobility'] });
    },
  });
}

/**
 * Log a finished movement break run to the day.
 *
 * No optimistic update: the point of the write is that it reaches the log, and
 * showing "logged" before the server has said so would make the one thing the
 * user cares about — whether the run counted — look settled while it is not.
 */
export function useLogMovementBreak() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (log: MovementBreakLog) => {
      const response = await mobilityApi.logMovementBreak(log);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workouts'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      queryClient.invalidateQueries({ queryKey: ['exercises'] });
      queryClient.invalidateQueries({ queryKey: ['exercises', 'movement-breaks'] });
      queryClient.invalidateQueries({ queryKey: ['progression'] });
    },
  });
}
