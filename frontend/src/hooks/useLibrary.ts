import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { libraryApi, programsApi } from "@/lib/api";
import type { BuilderModel } from "@/types/library";

/** The library listing: blocks and programs, yours and built-in (plan 0022). */
export function useLibrary() {
    return useQuery({
        queryKey: ["library"],
        queryFn: async () => (await libraryApi.get()).data,
    });
}

export function useBuiltinBlock(key: string | undefined) {
    return useQuery({
        queryKey: ["library", "block", key],
        queryFn: async () => (await libraryApi.getBuiltinBlock(key!)).data,
        enabled: !!key,
    });
}

/** Everything that lists blocks or programs reads one of these keys. */
function useInvalidateLibrary() {
    const queryClient = useQueryClient();
    return () => {
        queryClient.invalidateQueries({ queryKey: ["library"] });
        queryClient.invalidateQueries({ queryKey: ["programs"] });
        queryClient.invalidateQueries({ queryKey: ["workout-presets"] });
    };
}

export function useDuplicateBuiltinBlock() {
    const invalidate = useInvalidateLibrary();
    return useMutation({
        mutationFn: async (key: string) => (await libraryApi.duplicateBuiltinBlock(key)).data,
        onSettled: invalidate,
    });
}

export function usePrograms() {
    return useQuery({
        queryKey: ["programs"],
        queryFn: async () => (await programsApi.getAll()).data,
    });
}

export function useProgram(id: number | undefined) {
    return useQuery({
        queryKey: ["programs", id],
        queryFn: async () => (await programsApi.getById(id!)).data,
        enabled: id != null && !Number.isNaN(id),
    });
}

export function useCreateProgram() {
    const invalidate = useInvalidateLibrary();
    return useMutation({
        mutationFn: async (program: { name: string; script?: string; builder?: BuilderModel | null }) =>
            (await programsApi.create(program)).data,
        onSettled: invalidate,
    });
}

export function useUpdateProgram() {
    const invalidate = useInvalidateLibrary();
    return useMutation({
        mutationFn: async ({
            id,
            changes,
        }: {
            id: number;
            changes: { name?: string; script?: string; builder?: BuilderModel | null };
        }) => (await programsApi.update(id, changes)).data,
        onSettled: invalidate,
    });
}

export function useDeleteProgram() {
    const invalidate = useInvalidateLibrary();
    return useMutation({
        mutationFn: async (id: number) => {
            await programsApi.delete(id);
            return id;
        },
        onSettled: invalidate,
    });
}
