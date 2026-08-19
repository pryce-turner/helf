/**
 * The day view's per-set mobility flag.
 *
 * Worth mounting because nothing else can answer what it answers. The movement
 * cannot — a good morning is a loaded hinge in one session and a loaded
 * stretch in the next — and neither can the day, because a mobility routine
 * run alongside lifting is one day and two sessions. The flag is on the set,
 * and the most recent day carrying one is what the agent reads back over MCP
 * to write the next session from.
 *
 * The rule easiest to lose in a refactor is the one asserted last: a PUT that
 * only meant to change something else must not clear the flag on its way past.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import WorkoutSession from "./WorkoutSession";
import {
    categoriesApi,
    exercisesApi,
    progressionApi,
    workoutsApi,
} from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        workoutsApi: {
            getAll: vi.fn(),
            getById: vi.fn(),
            getCalendar: vi.fn(),
            create: vi.fn(),
            update: vi.fn(),
            delete: vi.fn(),
            bulkReorder: vi.fn(),
            toggleComplete: vi.fn(),
            moveToDate: vi.fn(),
            copyToDate: vi.fn(),
        },
        exercisesApi: {
            getAll: vi.fn(),
            getRecent: vi.fn(),
            getByName: vi.fn(),
            create: vi.fn(),
            update: vi.fn(),
            delete: vi.fn(),
            seed: vi.fn(),
        },
        categoriesApi: {
            getAll: vi.fn(),
            getByName: vi.fn(),
            create: vi.fn(),
            getExercises: vi.fn(),
        },
        progressionApi: {
            getMainLifts: vi.fn(),
            getByExercise: vi.fn(),
            getExerciseList: vi.fn(),
        },
    };
});

const workouts = vi.mocked(workoutsApi);

const DATE = "2026-08-11";

const set = (overrides: Record<string, unknown> = {}) => ({
    doc_id: 1,
    date: DATE,
    exercise: "Weighted Pigeon Squat",
    category: "Legs",
    weight: 30,
    weight_unit: "lbs",
    reps: 5,
    distance: null,
    distance_unit: null,
    time: null,
    comment: null,
    order: 1,
    completed_at: null,
    is_mobility: false,
    created_at: `${DATE}T09:00:00`,
    updated_at: `${DATE}T09:00:00`,
    ...overrides,
});

const renderDay = () =>
    renderPage(<WorkoutSession />, `/day/${DATE}`, "/day/:date");

const toggle = () => screen.getByRole("checkbox", { name: /mobility work/i });

/** A promise the test settles by hand, to look at the page mid-flight. */
const deferred = <T,>() => {
    let settle!: { resolve: (value: T) => void; reject: (error: Error) => void };
    const promise = new Promise<T>((resolve, reject) => {
        settle = { resolve, reject };
    });
    // Nothing awaits a rejection until the test triggers it, and an unhandled
    // one fails the run before the assertion it exists for.
    promise.catch(() => {});
    return { promise, ...settle };
};

beforeEach(() => {
    vi.clearAllMocks();
    workouts.getAll.mockResolvedValue({ data: [set()] } as never);
    vi.mocked(exercisesApi).getAll.mockResolvedValue({ data: [] } as never);
    vi.mocked(exercisesApi).getRecent.mockResolvedValue({ data: [] } as never);
    vi.mocked(categoriesApi).getAll.mockResolvedValue({ data: [] } as never);
    vi.mocked(progressionApi).getByExercise.mockResolvedValue({
        data: { exercise: "", data_points: [] },
    } as never);
    // A write moves what a read returns. Without that the toggle settles back
    // to its old value the moment the query refetches, and every assertion
    // about persistence passes for the wrong reason.
    workouts.update.mockImplementation((async (id: number, body: Record<string, unknown>) => {
        const written = set({ doc_id: id, ...body });
        workouts.getAll.mockResolvedValue({ data: [written] } as never);
        return { data: written };
    }) as never);
});

it("shows a set as not mobility work until it is marked", async () => {
    renderDay();

    await waitFor(() => expect(toggle()).toHaveAttribute("aria-checked", "false"));
});

it("marks a set as mobility work", async () => {
    renderDay();
    await waitFor(() => expect(toggle()).toBeInTheDocument());

    await userEvent.click(toggle());

    await waitFor(() =>
        expect(workouts.update).toHaveBeenCalledWith(
            1,
            expect.objectContaining({ is_mobility: true }),
        ),
    );
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-checked", "true"));
});

it("unmarks a set that was marked", async () => {
    workouts.getAll.mockResolvedValue({ data: [set({ is_mobility: true })] } as never);
    renderDay();
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-checked", "true"));

    await userEvent.click(toggle());

    await waitFor(() =>
        expect(workouts.update).toHaveBeenCalledWith(
            1,
            expect.objectContaining({ is_mobility: false }),
        ),
    );
});

it("sends the rest of the set unchanged, so the flag is the only edit", async () => {
    workouts.getAll.mockResolvedValue({
        data: [set({ comment: "right side failed at 4", reps: 4 })],
    } as never);
    renderDay();
    await waitFor(() => expect(toggle()).toBeInTheDocument());

    await userEvent.click(toggle());

    await waitFor(() =>
        expect(workouts.update).toHaveBeenCalledWith(
            1,
            expect.objectContaining({
                is_mobility: true,
                comment: "right side failed at 4",
                reps: 4,
                exercise: "Weighted Pigeon Squat",
            }),
        ),
    );
});

it("flags one set of a mixed day without touching the others", async () => {
    workouts.getAll.mockResolvedValue({
        data: [
            set({ doc_id: 1, exercise: "Lock 3", order: 1 }),
            set({ doc_id: 2, exercise: "Overhead Press", order: 2 }),
        ],
    } as never);
    renderDay();
    await waitFor(() =>
        expect(screen.getAllByRole("checkbox", { name: /mobility work/i })).toHaveLength(2),
    );

    await userEvent.click(screen.getAllByRole("checkbox", { name: /mobility work/i })[0]);

    await waitFor(() => expect(workouts.update).toHaveBeenCalledTimes(1));
    expect(workouts.update).toHaveBeenCalledWith(1, expect.objectContaining({ is_mobility: true }));
});

it("shows the new state while the write is still in flight", async () => {
    const write = deferred<{ data: unknown }>();
    workouts.update.mockReturnValue(write.promise as never);
    renderDay();
    await waitFor(() => expect(toggle()).toBeInTheDocument());

    await userEvent.click(toggle());

    // Optimistic: a toggle that waits for the server reads as one that did not
    // register the tap.
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-checked", "true"));
    write.resolve({ data: set({ is_mobility: true }) });
});

it("rolls back when the write fails, rather than showing a flag that was never saved", async () => {
    const write = deferred<{ data: unknown }>();
    workouts.update.mockReturnValue(write.promise as never);
    renderDay();
    await waitFor(() => expect(toggle()).toBeInTheDocument());

    await userEvent.click(toggle());
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-checked", "true"));

    write.reject(new Error("offline"));

    // The flag decides which day the agent reads back, so a false positive
    // here sends the next prescription off a session that never happened.
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-checked", "false"));
});
