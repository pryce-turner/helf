import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { exercisesApi, categoriesApi } from '@/lib/api';
import type { Exercise, ExerciseCreate, ExerciseUpdate, CategoryCreate, SeedExercisesResponse } from '@/types/exercise';

export function useExercises() {
  return useQuery({
    queryKey: ['exercises'],
    queryFn: async () => {
      const response = await exercisesApi.getAll();
      return response.data;
    },
  });
}

export function useRecentExercises(limit: number = 10) {
  return useQuery({
    queryKey: ['exercises', 'recent', limit],
    queryFn: async () => {
      const response = await exercisesApi.getRecent(limit);
      return response.data;
    },
  });
}

export function useExercise(name: string) {
  return useQuery({
    queryKey: ['exercises', name],
    queryFn: async () => {
      const response = await exercisesApi.getByName(name);
      return response.data;
    },
    enabled: !!name,
  });
}

export function useCreateExercise() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (exercise: ExerciseCreate) => {
      const response = await exercisesApi.create(exercise);
      return response.data;
    },
    onMutate: async (newExercise) => {
      await queryClient.cancelQueries({ queryKey: ['exercises'] });

      const previousExercises = queryClient.getQueriesData<Exercise[]>({ queryKey: ['exercises'] });

      const optimisticExercise: Exercise = {
        doc_id: -Date.now(),
        name: newExercise.name,
        category: newExercise.category,
        notes: newExercise.notes ?? null,
        last_used: null,
        use_count: 0,
        created_at: new Date().toISOString(),
      };

      queryClient.setQueriesData<Exercise[]>(
        { queryKey: ['exercises'] },
        (old) => old ? [...old, optimisticExercise] : [optimisticExercise]
      );

      return { previousExercises };
    },
    onError: (_err, _newExercise, context) => {
      context?.previousExercises.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['exercises'] });
    },
  });
}

export function useUpdateExercise() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: ExerciseUpdate }) => {
      const response = await exercisesApi.update(id, data);
      return response.data;
    },
    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: ['exercises'] });

      const previousExercises = queryClient.getQueriesData<Exercise[]>({ queryKey: ['exercises'] });

      queryClient.setQueriesData<Exercise[]>(
        { queryKey: ['exercises'] },
        (old) => old?.map((e) =>
          e.doc_id === id ? { ...e, ...data } : e
        )
      );

      return { previousExercises };
    },
    onError: (_err, _vars, context) => {
      context?.previousExercises.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['exercises'] });
    },
  });
}

export function useDeleteExercise() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: number) => {
      await exercisesApi.delete(id);
    },
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['exercises'] });

      const previousExercises = queryClient.getQueriesData<Exercise[]>({ queryKey: ['exercises'] });

      queryClient.setQueriesData<Exercise[]>(
        { queryKey: ['exercises'] },
        (old) => old?.filter((e) => e.doc_id !== id)
      );

      return { previousExercises };
    },
    onError: (_err, _id, context) => {
      context?.previousExercises.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['exercises'] });
    },
  });
}

export function useSeedExercises() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (): Promise<SeedExercisesResponse> => {
      const response = await exercisesApi.seed();
      return response.data;
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['exercises'] });
      queryClient.invalidateQueries({ queryKey: ['categories'] });
    },
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: async () => {
      const response = await categoriesApi.getAll();
      return response.data;
    },
  });
}

export function useCategory(name: string) {
  return useQuery({
    queryKey: ['categories', name],
    queryFn: async () => {
      const response = await categoriesApi.getByName(name);
      return response.data;
    },
    enabled: !!name,
  });
}

export function useCategoryExercises(name: string) {
  return useQuery({
    queryKey: ['categories', name, 'exercises'],
    queryFn: async () => {
      const response = await categoriesApi.getExercises(name);
      return response.data;
    },
    enabled: !!name,
  });
}

export function useCreateCategory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (category: CategoryCreate) => {
      const response = await categoriesApi.create(category);
      return response.data;
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
    },
  });
}
