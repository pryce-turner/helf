import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { mobilityApi } from '../lib/api';

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
    mutationFn: async (date: string) => {
      const response = await mobilityApi.transfer(date);
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
    mutationFn: async () => {
      await mobilityApi.clearPending();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mobility'] });
    },
  });
}
