import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { mobilityApi } from '../lib/api';
import type { MobilityDay } from '../types/mobility';

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

export function useMobilityDay(date: string | undefined) {
  return useQuery({
    queryKey: ['mobility', 'day', date],
    queryFn: async () => {
      const response = await mobilityApi.getDay(date!);
      return response.data;
    },
    enabled: !!date,
  });
}

export function useSetMobilityDay() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ date, isMobility }: { date: string; isMobility: boolean }) => {
      const response = await mobilityApi.setDay(date, isMobility);
      return response.data;
    },
    // Optimistic here, unlike transfer. A checkbox that waits for the server
    // reads as one that did not register the tap, and the failure mode is the
    // opposite of transfer's: nothing is written that a second tap could
    // duplicate, because the same state sent twice means the same thing.
    onMutate: async ({ date, isMobility }) => {
      const key = ['mobility', 'day', date];
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<MobilityDay>(key);

      queryClient.setQueryData<MobilityDay>(key, {
        date,
        is_mobility: isMobility,
        // Unmarking drops the agent's reasoning with the marker — they are one
        // row — so the optimistic state has to drop it too.
        rationale: isMobility ? (previous?.rationale ?? null) : null,
      });

      return { key, previous };
    },
    onError: (_error, _variables, context) => {
      if (context) {
        queryClient.setQueryData(context.key, context.previous);
      }
    },
    // The marked day is what the agent reads the next session back from, so
    // the mobility tab's `last_session` changes with it.
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['mobility'] });
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
