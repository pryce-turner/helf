/**
 * The day view's one assertion about the session rather than about a set in it:
 * whether the day was a mobility day.
 *
 * Worth mounting because nothing else can answer it. The rows cannot — a
 * mobility routine borrows movements that are also lifting movements — so the
 * checkbox is the fact, and what the agent reads back over MCP to write the
 * next session from. The two rules that are easy to lose in a refactor are the
 * ones asserted here: an empty day cannot be marked, and a day already marked
 * stays togglable so a mistake can be undone.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import WorkoutSession from "./WorkoutSession";
import {
    categoriesApi,
    exercisesApi,
    mobilityApi,
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
        mobilityApi: {
            getPending: vi.fn(),
            transfer: vi.fn(),
            clearPending: vi.fn(),
            getDay: vi.fn(),
            setDay: vi.fn(),
        },
    };
});

const workouts = vi.mocked(workoutsApi);
const mobility = vi.mocked(mobilityApi);

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
    created_at: `${DATE}T09:00:00`,
    ...overrides,
});

const day = (overrides: Record<string, unknown> = {}) => ({
    date: DATE,
    is_mobility: false,
    rationale: null,
    ...overrides,
});

const renderDay = () =>
    renderPage(<WorkoutSession />, `/day/${DATE}`, "/day/:date");

const checkbox = () => screen.getByRole("checkbox", { name: /mobility session/i });

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
    mobility.getDay.mockResolvedValue({ data: day() } as never);
    // A write moves what a read returns. Without that the toggle settles back
    // to the stale stub, and every assertion after a click is about the mock.
    mobility.setDay.mockImplementation((async (date: string, isMobility: boolean) => {
        const written = day({ date, is_mobility: isMobility });
        mobility.getDay.mockResolvedValue({ data: written } as never);
        return { data: written };
    }) as never);
    mobility.getPending.mockResolvedValue({
        data: { ready: false, items: [], rationale: null, generated_at: null, last_session: null },
    } as never);
    vi.mocked(progressionApi).getByExercise.mockResolvedValue({
        data: { exercise: "", historical: [], projected: [] },
    } as never);
});

it("marks the day as a mobility session", async () => {
    const user = userEvent.setup();
    renderDay();

    await waitFor(() => expect(checkbox()).toHaveAttribute("aria-checked", "false"));
    await user.click(checkbox());

    expect(mobility.setDay).toHaveBeenCalledWith(DATE, true);
    await waitFor(() => expect(checkbox()).toHaveAttribute("aria-checked", "true"));
});

it("registers the tap before the server answers", async () => {
    const user = userEvent.setup();
    const write = deferred<{ data: ReturnType<typeof day> }>();
    mobility.setDay.mockReturnValue(write.promise as never);
    renderDay();

    await waitFor(() => expect(checkbox()).toHaveAttribute("aria-checked", "false"));
    await user.click(checkbox());

    // Still in flight. A checkbox that waits for the round trip reads as one
    // that did not register the tap, and gets tapped again.
    expect(checkbox()).toHaveAttribute("aria-checked", "true");
    write.resolve({ data: day({ is_mobility: true }) });
});

it("unmarks a day that is already marked", async () => {
    const user = userEvent.setup();
    mobility.getDay.mockResolvedValue({ data: day({ is_mobility: true }) } as never);
    renderDay();

    await waitFor(() => expect(checkbox()).toHaveAttribute("aria-checked", "true"));
    await user.click(checkbox());

    expect(mobility.setDay).toHaveBeenCalledWith(DATE, false);
    await waitFor(() => expect(checkbox()).toHaveAttribute("aria-checked", "false"));
});

it("will not mark a day with nothing logged", async () => {
    workouts.getAll.mockResolvedValue({ data: [] } as never);
    renderDay();

    // Marking one would hand the agent an empty day as its most recent input.
    await waitFor(() => expect(checkbox()).toBeDisabled());
});

it("still lets a marked day be unmarked after its sets are gone", async () => {
    const user = userEvent.setup();
    workouts.getAll.mockResolvedValue({ data: [] } as never);
    mobility.getDay.mockResolvedValue({ data: day({ is_mobility: true }) } as never);
    renderDay();

    await waitFor(() => expect(checkbox()).toHaveAttribute("aria-checked", "true"));
    expect(checkbox()).toBeEnabled();

    await user.click(checkbox());
    expect(mobility.setDay).toHaveBeenCalledWith(DATE, false);
});

it("warns before discarding reasoning the agent wrote", async () => {
    mobility.getDay.mockResolvedValue({
        data: day({ is_mobility: true, rationale: "Pigeon leads, right side first." }),
    } as never);
    renderDay();

    // The marker and the rationale are one row, so unchecking deletes both.
    await waitFor(() =>
        expect(screen.getByText(/unchecking discards its reasoning/i)).toBeInTheDocument(),
    );
});

it("reverts the checkbox when the write fails", async () => {
    const user = userEvent.setup();
    const write = deferred<{ data: ReturnType<typeof day> }>();
    mobility.setDay.mockReturnValue(write.promise as never);
    renderDay();

    await waitFor(() => expect(checkbox()).toHaveAttribute("aria-checked", "false"));
    await user.click(checkbox());
    expect(checkbox()).toHaveAttribute("aria-checked", "true");

    // The day is the agent's input, so a box left checked over a write that
    // never landed is worse than one that never moved.
    write.reject(new Error("offline"));
    await waitFor(() => expect(checkbox()).toHaveAttribute("aria-checked", "false"));
});
