import { useQuery } from '@tanstack/react-query';
import { progressionApi } from '@/lib/api';

export function useProgression(exercise: string, includeUpcoming: boolean = true) {
  return useQuery({
    queryKey: ['progression', exercise, includeUpcoming],
    queryFn: async () => {
      const response = await progressionApi.getByExercise(exercise, includeUpcoming);
      return response.data;
    },
    enabled: !!exercise,
  });
}

export function useMainLiftsProgression() {
  return useQuery({
    queryKey: ['progression', 'main-lifts'],
    queryFn: async () => {
      const response = await progressionApi.getMainLifts();
      return response.data;
    },
  });
}

export function useProgressionExercises() {
  return useQuery({
    queryKey: ['progression', 'exercises'],
    queryFn: async () => {
      const response = await progressionApi.getExerciseList();
      return response.data;
    },
  });
}
