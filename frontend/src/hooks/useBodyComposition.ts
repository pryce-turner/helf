import {
  keepPreviousData,
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import { bodyCompositionApi, systemApi } from '@/lib/api';
import {
  drainScale,
  ScaleError,
  type ScaleCredentials,
} from '@/lib/scale';
import type { BodyComposition } from '@/types/bodyComposition';

export function useBodyCompositions(params?: {
  start_date?: string;
  end_date?: string;
  skip?: number;
  limit?: number;
  sort?: 'observed' | 'ingested';
}) {
  return useQuery({
    queryKey: ['body-composition', params],
    queryFn: async () => {
      const response = await bodyCompositionApi.getAll(params);
      return response.data;
    },
  });
}

export function useLatestBodyComposition() {
  return useQuery({
    queryKey: ['body-composition', 'latest'],
    queryFn: async () => {
      const response = await bodyCompositionApi.getLatest();
      return response.data;
    },
  });
}

export function useBodyCompositionStats() {
  return useQuery({
    queryKey: ['body-composition', 'stats'],
    queryFn: async () => {
      const response = await bodyCompositionApi.getStats();
      return response.data;
    },
  });
}

export function useBodyCompositionTrends(days: number = 30) {
  return useQuery({
    queryKey: ['body-composition', 'trends', days],
    queryFn: async () => {
      const response = await bodyCompositionApi.getTrends(days);
      return response.data;
    },
    // Changing the period is a filter, not a navigation: hold the charts that
    // are already drawn rather than replacing four of them with a spinner and
    // collapsing the page to nothing for the length of a request.
    placeholderData: keepPreviousData,
  });
}

export function useCreateBodyComposition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (measurement: Partial<BodyComposition>) => {
      const response = await bodyCompositionApi.create(measurement);
      return response.data;
    },
    onMutate: async (newMeasurement) => {
      await queryClient.cancelQueries({ queryKey: ['body-composition'] });

      const previousData = queryClient.getQueriesData<BodyComposition[]>({ queryKey: ['body-composition'] });

      const optimistic: BodyComposition = {
        doc_id: -Date.now(),
        timestamp: new Date().toISOString(),
        date: new Date().toISOString().split('T')[0],
        weight: newMeasurement.weight ?? 0,
        weight_unit: newMeasurement.weight_unit ?? 'lbs',
        body_fat_pct: newMeasurement.body_fat_pct ?? null,
        muscle_mass: newMeasurement.muscle_mass ?? null,
        bmi: newMeasurement.bmi ?? null,
        water_pct: newMeasurement.water_pct ?? null,
        bone_mass_kg: newMeasurement.bone_mass_kg ?? null,
        visceral_fat: newMeasurement.visceral_fat ?? null,
        metabolic_age: newMeasurement.metabolic_age ?? null,
        protein_pct: newMeasurement.protein_pct ?? null,
        created_at: new Date().toISOString(),
        source: 'manual',
      };

      queryClient.setQueriesData<BodyComposition[]>(
        { queryKey: ['body-composition'] },
        (old) => old ? [...old, optimistic] : [optimistic]
      );

      return { previousData };
    },
    onError: (_err, _newMeasurement, context) => {
      context?.previousData.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['body-composition'] });
    },
  });
}

export function useDeleteBodyComposition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: number) => {
      await bodyCompositionApi.delete(id);
      return id;
    },
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['body-composition'] });

      const previousData = queryClient.getQueriesData<BodyComposition[]>({ queryKey: ['body-composition'] });

      // `setQueriesData` runs this updater against *every* query under the
      // ['body-composition'] prefix, and they do not all hold lists — 'stats'
      // and 'trends' hold objects. Calling .filter on those throws, which
      // kills onMutate, which means the mutation never reaches the network:
      // the row just sits there and no request is made. The Array check is
      // what makes the prefix match safe.
      queryClient.setQueriesData<BodyComposition[]>(
        { queryKey: ['body-composition'] },
        (old) => (Array.isArray(old) ? old.filter((m) => m.doc_id !== id) : old)
      );

      return { previousData };
    },
    onError: (_err, _id, context) => {
      context?.previousData.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['body-composition'] });
    },
  });
}


/**
 * Trigger a BodySpec import.
 *
 * The token is an argument to the mutation, never held in this hook, never
 * cached by React Query, and never written to storage. Its whole lifetime is
 * the request - see docs/plans/0008-bodyspec-integration.md §3.
 */
export function useSyncBodySpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (token: string) => {
      const response = await bodyCompositionApi.syncBodySpec(token);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['body-composition'] });
    },
  });
}

/**
 * How long Helf gets to answer before the drain is called off. It runs
 * alongside the Bluetooth connect, so on a reachable server it costs nothing;
 * the cap only matters when a tailnet address is silently dropping packets.
 */
const HELF_REACHABLE_MS = 4_000;

async function helfReachable(): Promise<void> {
  try {
    await systemApi.health(HELF_REACHABLE_MS);
  } catch (cause) {
    throw new ScaleError(
      "Helf is unreachable — is Tailscale up? The scale was not read, so its readings are still on it.",
      { cause },
    );
  }
}

/**
 * Read the scale over Web Bluetooth and hand the whole drain to the server.
 *
 * A mutation rather than a query because it is strictly user-initiated: Web
 * Bluetooth requires a gesture per connection and cannot run in a service
 * worker, so there is nothing here that React Query could refetch on its own.
 */
export function useScaleDrain() {
  const queryClient = useQueryClient();

  return useMutation({
    // `pick` decides which of the two connect paths runs: the quiet one that
    // dials an awake scale, or the chooser that wakes a sleeping one. It is a
    // mutation variable rather than a hook option because the page flips it
    // between the first tap and the second.
    mutationFn: async ({
      credentials,
      pick,
    }: {
      credentials: ScaleCredentials;
      pick?: boolean;
    }) => {
      const { readings, bodyCompositionPackets } = await drainScale(
        credentials,
        { pick, reachable: helfReachable },
      );

      // Surfaced to the page because a weight-only drain is a real, silent
      // degradation: the scale answers, the numbers look right, and body fat,
      // muscle and water are simply missing. The BF720 needs a real user
      // profile to compute them, so this is worth saying out loud rather than
      // leaving as four empty columns.
      const weightOnly = readings.length > 0 && bodyCompositionPackets === 0;

      if (readings.length === 0) {
        return {
          readings_received: 0,
          imported: 0,
          skipped: 0,
          weightOnly,
        };
      }
      const response = await bodyCompositionApi.syncScale(readings);
      return { ...response.data, weightOnly };
    },
    onSuccess: (result) => {
      // Only worth invalidating if something actually landed - a drain that
      // is entirely replay is the common case and changes nothing on screen.
      if (result.imported > 0) {
        queryClient.invalidateQueries({ queryKey: ['body-composition'] });
      }
    },
  });
}
