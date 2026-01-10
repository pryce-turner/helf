import axios from "axios";
import type {
    Workout,
    WorkoutCreate,
    CalendarResponse,
} from "../types/workout";
import type {
    Exercise,
    ExerciseCreate,
    ExerciseUpdate,
    Category,
    CategoryCreate,
    SeedExercisesResponse,
} from "../types/exercise";
import type {
    BodyComposition,
    BodyCompositionStats,
    BodyCompositionTrend,
} from "../types/bodyComposition";
import type { ProgressionResponse } from "../types/progression";
import type {
    UpcomingWorkout,
    UpcomingWorkoutCreate,
    WendlerCurrentMaxes,
    LiftoscriptGenerateRequest,
    LiftoscriptGenerateResponse,
    PresetInfo,
    PresetContent,
} from "../types/upcoming";

// Use relative URL - Vite proxy handles routing to backend in dev
// In production, requests go to same origin
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        "Content-Type": "application/json",
    },
});

// Workouts
export const workoutsApi = {
    getAll: (params?: { date?: string; skip?: number; limit?: number }) =>
        api.get<Workout[]>("/api/workouts/", { params }),

    getById: (id: number) => api.get<Workout>(`/api/workouts/${id}`),

    getCalendar: (year: number, month: number) =>
        api.get<CalendarResponse>("/api/workouts/calendar", {
            params: { year, month },
        }),

    create: (workout: WorkoutCreate) =>
        api.post<Workout>("/api/workouts/", workout),

    update: (id: number, workout: WorkoutCreate) =>
        api.put<Workout>(`/api/workouts/${id}`, workout),

    delete: (id: number) => api.delete(`/api/workouts/${id}`),

    bulkReorder: (workoutIds: number[]) =>
        api.patch("/api/workouts/reorder", { workout_ids: workoutIds }),

    toggleComplete: (id: number, completed: boolean) =>
        api.patch<Workout>(`/api/workouts/${id}/complete`, { completed }),

    moveToDate: (sourceDate: string, targetDate: string) =>
        api.post<{
            source_date: string;
            target_date: string;
            count: number;
            message: string;
        }>(`/api/workouts/date/${sourceDate}/move`, { target_date: targetDate }),
};

// Exercises
export const exercisesApi = {
    getAll: () => api.get<Exercise[]>("/api/exercises/"),

    getRecent: (limit: number = 10) =>
        api.get<Exercise[]>("/api/exercises/recent", { params: { limit } }),

    getByName: (name: string) =>
        api.get<Exercise>(`/api/exercises/${encodeURIComponent(name)}`),

    create: (exercise: ExerciseCreate) =>
        api.post<Exercise>("/api/exercises/", exercise),

    update: (id: number, exercise: ExerciseUpdate) =>
        api.put<Exercise>(`/api/exercises/${id}`, exercise),

    delete: (id: number) => api.delete(`/api/exercises/${id}`),

    seed: () => api.post<SeedExercisesResponse>("/api/exercises/seed"),
};

// Categories
export const categoriesApi = {
    getAll: () => api.get<Category[]>("/api/exercises/categories/"),

    getByName: (name: string) =>
        api.get<Category>(
            `/api/exercises/categories/${encodeURIComponent(name)}`,
        ),

    create: (category: CategoryCreate) =>
        api.post<Category>("/api/exercises/categories/", category),

    getExercises: (name: string) =>
        api.get<{ category: string; exercises: string[] }>(
            `/api/exercises/categories/${encodeURIComponent(name)}/exercises`,
        ),
};

// Progression
export const progressionApi = {
    getByExercise: (exercise: string, includeUpcoming: boolean = true) =>
        api.get<ProgressionResponse>(
            `/api/progression/${encodeURIComponent(exercise)}`,
            {
                params: { include_upcoming: includeUpcoming },
            },
        ),

    getMainLifts: () =>
        api.get<Record<string, ProgressionResponse>>("/api/progression/"),

    getExerciseList: () => api.get<string[]>("/api/progression/exercises/list"),
};

// Upcoming Workouts
export const upcomingApi = {
    getAll: () => api.get<UpcomingWorkout[]>("/api/upcoming/"),

    getSession: (session: number) =>
        api.get<UpcomingWorkout[]>(`/api/upcoming/session/${session}`),

    create: (workout: UpcomingWorkoutCreate) =>
        api.post<UpcomingWorkout>("/api/upcoming/", workout),

    createBulk: (workouts: UpcomingWorkoutCreate[]) =>
        api.post<UpcomingWorkout[]>("/api/upcoming/bulk", { workouts }),

    deleteSession: (session: number) =>
        api.delete(`/api/upcoming/session/${session}`),

    transferSession: (session: number, date: string) =>
        api.post<{
            session: number;
            date: string;
            count: number;
            message: string;
        }>(`/api/upcoming/session/${session}/transfer`, { date }),

    getWendlerMaxes: () =>
        api.get<WendlerCurrentMaxes>("/api/upcoming/wendler/maxes"),

    // Liftoscript endpoints
    getPresets: () =>
        api.get<PresetInfo[]>("/api/upcoming/presets"),

    getPreset: (name: string) =>
        api.get<PresetContent>(`/api/upcoming/presets/${encodeURIComponent(name)}`),

    generateLiftoscript: (request: LiftoscriptGenerateRequest) =>
        api.post<LiftoscriptGenerateResponse>("/api/upcoming/liftoscript/generate", request),
};

// Body Composition
export const bodyCompositionApi = {
    getAll: (params?: {
        start_date?: string;
        end_date?: string;
        skip?: number;
        limit?: number;
    }) => api.get<BodyComposition[]>("/api/body-composition/", { params }),

    getLatest: () => api.get<BodyComposition>("/api/body-composition/latest"),

    getStats: () =>
        api.get<BodyCompositionStats>("/api/body-composition/stats"),

    getTrends: (days: number = 30) =>
        api.get<BodyCompositionTrend>("/api/body-composition/trends", {
            params: { days },
        }),

    create: (measurement: Partial<BodyComposition>) =>
        api.post<BodyComposition>("/api/body-composition/", measurement),

    delete: (id: number) => api.delete(`/api/body-composition/${id}`),
};

// System
export const systemApi = {
    health: () => api.get<{ status: string; version: string }>("/api/health"),

    mqttStatus: () =>
        api.get<{ connected: boolean; broker: string }>("/api/mqtt/status"),

    mqttReconnect: () => api.post<{ message: string }>("/api/mqtt/reconnect"),
};

export default api;
