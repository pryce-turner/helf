import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { bodyCompositionApi } from '@/lib/api';
import type { BodyComposition } from '@/types/bodyComposition';

export function useBodyCompositions(params?: {
  start_date?: string;
  end_date?: string;
  skip?: number;
  limit?: number
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

      queryClient.setQueriesData<BodyComposition[]>(
        { queryKey: ['body-composition'] },
        (old) => old?.filter((m) => m.doc_id !== id)
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
