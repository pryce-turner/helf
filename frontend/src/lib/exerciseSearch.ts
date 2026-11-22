import type { Exercise } from "@/types/exercise";

/**
 * The add form's exercise search (ExerciseSearch). Ranking: the name starts
 * with a term, then a word in it does, then it appears anywhere; every
 * whitespace-separated term must match; ties go to the movement used most.
 */
const MAX_RESULTS = 8;

const rank = (name: string, terms: string[]): number | null => {
    const lower = name.toLowerCase();
    const words = lower.split(/[\s\-/()]+/);
    let score = 0;
    for (const term of terms) {
        if (lower.startsWith(term)) score += 0;
        else if (words.some((w) => w.startsWith(term))) score += 1;
        else if (lower.includes(term)) score += 2;
        else return null;
    }
    return score;
};

export function matchExercises(exercises: Exercise[], query: string): Exercise[] {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (terms.length === 0) return [];
    return exercises
        .map((exercise) => ({ exercise, score: rank(exercise.name, terms) }))
        .filter((m): m is { exercise: Exercise; score: number } => m.score !== null)
        .sort(
            (a, b) =>
                a.score - b.score ||
                b.exercise.use_count - a.exercise.use_count ||
                a.exercise.name.localeCompare(b.exercise.name),
        )
        .slice(0, MAX_RESULTS)
        .map((m) => m.exercise);
}
