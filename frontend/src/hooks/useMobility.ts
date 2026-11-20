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
 * Insert a suggested, incomplete mobility tile on a date (plan 0018).
 *
 * No optimistic update: the tile is created server-side from the shuffle, so
 * there is nothing honest to paint before the answer lands. The button is
 * disabled while pending instead, which is the guard against a double tap
 * inserting two.
 *
 * A suggestion is *not* work yet: the calendar (performed tiles only) and the
 * exercise's `last_used` are untouched by it, so only `workouts` refetches.
 */
export function useSuggestMovementBreak() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (date?: string) => {
      const response = await mobilityApi.suggestMovementBreak(date);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workouts'] });
    },
  });
}
