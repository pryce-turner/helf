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
    onSuccess: () => {
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['body-composition'] });
    },
  });
}
