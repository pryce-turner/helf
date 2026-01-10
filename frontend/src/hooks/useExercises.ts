import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { exercisesApi, categoriesApi } from '@/lib/api';
import type { ExerciseCreate, ExerciseUpdate, CategoryCreate } from '@/types/exercise';

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
    onSuccess: () => {
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
    onSuccess: () => {
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['exercises'] });
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
    },
  });
}
