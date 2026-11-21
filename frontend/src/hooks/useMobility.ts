import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { mobilityApi } from '../lib/api';

/**
 * The last mobility session that reached the calendar, with its sets and
 * their comments — the read-back the next prescription is written from.
 * Null when no set has ever been flagged.
 */
export function useLastMobilitySession() {
  return useQuery({
    queryKey: ['mobility', 'last-session'],
    queryFn: async () => {
      const response = await mobilityApi.getLastSession();
      return response.data;
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
