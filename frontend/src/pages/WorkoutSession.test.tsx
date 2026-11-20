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
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import WorkoutSession from "./WorkoutSession";
import type { Workout } from "@/types/workout";
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
            setDayMobility: vi.fn(),
            perform: vi.fn(),
            recordRestAfter: vi.fn(),
        },
        exercisesApi: {
            getAll: vi.fn(),
            getRecent: vi.fn(),
            getMovementBreaks: vi.fn(),
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
            ...actual.mobilityApi,
            suggestMovementBreak: vi.fn(),
        },
    };
});

const workouts = vi.mocked(workoutsApi);
const suggest = vi.mocked(mobilityApi.suggestMovementBreak);

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
    work_seconds: null,
    rest_seconds: null,
    rest_after_seconds: null,
    completed_reps: null,
    actual_work_seconds: null,
    actual_rest_seconds: null,
    actual_rest_after_seconds: null,
    ended_early: false,
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
    vi.mocked(exercisesApi).getMovementBreaks.mockResolvedValue({
        data: [{ doc_id: 1, name: "Deep Squat Hold", category: "Legs" }],
    } as never);
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

it("marks every set on the day as mobility in one press", async () => {
    workouts.getAll.mockResolvedValue({
        data: [set({ doc_id: 1, order: 1 }), set({ doc_id: 2, exercise: "Lock 3", order: 2 })],
    } as never);
    workouts.setDayMobility.mockImplementation((async (date: string, isMobility: boolean) => {
        workouts.getAll.mockResolvedValue({
            data: [
                set({ doc_id: 1, order: 1, is_mobility: isMobility }),
                set({ doc_id: 2, exercise: "Lock 3", order: 2, is_mobility: isMobility }),
            ],
        } as never);
        return { data: { date, is_mobility: isMobility, changed: 2, total: 2, message: "" } };
    }) as never);
    renderDay();
    const button = await screen.findByRole("button", { name: /mark all mobility/i });

    await userEvent.click(button);

    await waitFor(() =>
        expect(workouts.setDayMobility).toHaveBeenCalledWith(DATE, true),
    );
    // One request, not one per set — every UPDATE writes an audit row.
    expect(workouts.setDayMobility).toHaveBeenCalledTimes(1);
    expect(workouts.update).not.toHaveBeenCalled();
});

it("offers to clear the day once every set is already mobility", async () => {
    workouts.getAll.mockResolvedValue({
        data: [set({ doc_id: 1, is_mobility: true })],
    } as never);
    renderDay();

    const button = await screen.findByRole("button", { name: /unmark all/i });
    await userEvent.click(button);

    await waitFor(() =>
        expect(workouts.setDayMobility).toHaveBeenCalledWith(DATE, false),
    );
});

it("still offers to mark when only some sets are flagged", async () => {
    workouts.getAll.mockResolvedValue({
        data: [
            set({ doc_id: 1, is_mobility: true, order: 1 }),
            set({ doc_id: 2, exercise: "Overhead Press", is_mobility: false, order: 2 }),
        ],
    } as never);
    renderDay();

    // A mixed day is a valid state, and the button's job is to leave it.
    expect(await screen.findByRole("button", { name: /mark all mobility/i })).toBeInTheDocument();
});

it("offers no bulk button on a day with nothing logged", async () => {
    workouts.getAll.mockResolvedValue({ data: [] } as never);
    renderDay();

    await waitFor(() => expect(workouts.getAll).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /mark all mobility|unmark all/i })).not.toBeInTheDocument();
});

it("rolls the whole day back when the bulk write fails", async () => {
    const write = deferred<{ data: unknown }>();
    workouts.setDayMobility.mockReturnValue(write.promise as never);
    renderDay();
    const button = await screen.findByRole("button", { name: /mark all mobility/i });

    await userEvent.click(button);
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-checked", "true"));

    write.reject(new Error("offline"));

    await waitFor(() => expect(toggle()).toHaveAttribute("aria-checked", "false"));
});

it("duplicates a mobility tile with the flag, as a planned tile", async () => {
    workouts.getAll.mockResolvedValue({
        data: [set({ is_mobility: true, work_seconds: 40 })],
    } as never);
    workouts.create.mockResolvedValue({ data: set() } as never);
    renderDay();

    // The tile body opens its editor.
    await userEvent.click(await screen.findByText("Weighted Pigeon Squat"));
    await userEvent.click(await screen.findByRole("button", { name: /duplicate/i }));

    // The intent travels; the performance does not (the new tile is planned,
    // so completion and actuals reset server-side).
    await waitFor(() =>
        expect(workouts.create).toHaveBeenCalledWith(
            expect.objectContaining({ is_mobility: true, work_seconds: 40 }),
        ),
    );
});

it("suggests a movement break onto the displayed date", async () => {
    suggest.mockResolvedValue({
        data: set({ doc_id: 9, exercise: "Deep Squat Hold", is_mobility: true }),
    } as never);
    renderDay();

    const button = await screen.findByRole("button", { name: /movement break/i });
    await userEvent.click(button);

    await waitFor(() => expect(suggest).toHaveBeenCalledWith(DATE));
});

it("cannot suggest twice from a double tap", async () => {
    const write = deferred<{ data: unknown }>();
    suggest.mockReturnValue(write.promise as never);
    renderDay();

    const button = await screen.findByRole("button", { name: /movement break/i });
    await userEvent.click(button);
    await userEvent.click(button);

    // Disabled while the write is in flight: a suggestion is created server-
    // side, and a second tap would insert a second tile.
    expect(suggest).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    write.resolve({ data: set({ doc_id: 9, exercise: "Deep Squat Hold" }) });
});

it("does not offer the shuffle when the pool is empty", async () => {
    vi.mocked(exercisesApi).getMovementBreaks.mockResolvedValue({ data: [] } as never);
    renderDay();

    await waitFor(() => expect(workouts.getAll).toHaveBeenCalled());
    expect(
        screen.queryByRole("button", { name: /movement break/i }),
    ).not.toBeInTheDocument();
});

// --- Exercise-driven tile fields and rest dividers (plan 0018) --------------

const farmerCarry = (overrides: Record<string, unknown> = {}) => ({
    doc_id: 20,
    name: "Farmer Carry",
    category: "Legs",
    form: null,
    application: null,
    rating: null,
    movement_break_enabled: true,
    reps_enabled: true,
    default_reps: 2,
    weight_enabled: true,
    default_weight_lb: null,
    distance_enabled: false,
    default_distance: null,
    default_distance_unit: null,
    time_enabled: true,
    default_work_seconds: 40,
    default_rest_seconds: 20,
    default_rest_after_seconds: 15,
    last_used: null,
    use_count: 0,
    created_at: "2026-11-01",
    ...overrides,
});

it("applies the exercise's defaults when one is picked in the add form", async () => {
    vi.mocked(exercisesApi).getAll.mockResolvedValue({
        data: [farmerCarry()],
    } as never);
    vi.mocked(categoriesApi).getAll.mockResolvedValue({
        data: [{ doc_id: 1, name: "Legs", created_at: "2026-01-01" }],
    } as never);
    renderDay();

    await userEvent.click(await screen.findByRole("button", { name: /add/i }));
    await userEvent.click(screen.getByRole("combobox", { name: "Category" }));
    await userEvent.click(await screen.findByRole("option", { name: "Legs" }));
    await userEvent.click(screen.getByRole("combobox", { name: "Exercise" }));
    await userEvent.click(await screen.findByRole("option", { name: "Farmer Carry" }));

    // Enabled with a NULL default: the input appears and starts blank.
    expect(screen.getByLabelText("Weight")).toHaveValue(null);
    // Timed defaults come along.
    expect(screen.getByLabelText("Reps")).toHaveValue(2);
    expect(screen.getByLabelText("Work seconds")).toHaveValue(40);
    expect(screen.getByLabelText("Rest seconds")).toHaveValue(20);
    expect(screen.getByLabelText("Rest after set seconds")).toHaveValue(15);
    // Distance is disabled on the movement: not offered.
    expect(screen.queryByLabelText(/distance/i)).not.toBeInTheDocument();
});

it("sends the tile's timing when a suggested set is saved", async () => {
    workouts.create.mockResolvedValue({ data: set() } as never);
    vi.mocked(exercisesApi).getAll.mockResolvedValue({
        data: [farmerCarry()],
    } as never);
    vi.mocked(categoriesApi).getAll.mockResolvedValue({
        data: [{ doc_id: 1, name: "Legs", created_at: "2026-01-01" }],
    } as never);
    renderDay();

    await userEvent.click(await screen.findByRole("button", { name: /add/i }));
    await userEvent.click(screen.getByRole("combobox", { name: "Category" }));
    await userEvent.click(await screen.findByRole("option", { name: "Legs" }));
    await userEvent.click(screen.getByRole("combobox", { name: "Exercise" }));
    await userEvent.click(await screen.findByRole("option", { name: "Farmer Carry" }));
    await userEvent.click(screen.getByRole("button", { name: /add workout/i }));

    await waitFor(() =>
        expect(workouts.create).toHaveBeenCalledWith(
            expect.objectContaining({
                exercise: "Farmer Carry",
                reps: 2,
                work_seconds: 40,
                rest_seconds: 20,
                rest_after_seconds: 15,
            }),
        ),
    );
});

it("keeps a tile's existing values visible in the editor even when the group is off", async () => {
    // The movement no longer offers Time — history is not rewritten by that
    // (plan 0018) — but a tile with timing on it still shows it.
    workouts.getAll.mockResolvedValue({
        data: [set({ work_seconds: 40, rest_seconds: 20, exercise: "Farmer Carry" })],
    } as never);
    vi.mocked(exercisesApi).getAll.mockResolvedValue({
        data: [farmerCarry({ time_enabled: false })],
    } as never);
    renderDay();

    await userEvent.click(
        await screen.findByText("Farmer Carry"),
    );

    expect(await screen.findByLabelText("Work seconds")).toHaveValue(40);
    expect(screen.getByLabelText("Rest seconds")).toHaveValue(20);
});

it("renders a rest divider after a tile that carries one, editable through it", async () => {
    workouts.getAll.mockResolvedValue({
        data: [
            set({ doc_id: 1, order: 1, rest_after_seconds: 15 }),
            set({ doc_id: 2, order: 2, exercise: "Overhead Press" }),
        ],
    } as never);
    renderDay();

    const divider = await screen.findByRole("button", { name: /rest 0:15/i });
    expect(divider).toBeInTheDocument();

    // The divider has no state of its own: editing it edits the preceding
    // tile, so it opens that tile's editor.
    await userEvent.click(divider);
    expect(await screen.findByLabelText("Rest after set seconds")).toHaveValue(15);
});

it("renders no divider for a zero rest-after", async () => {
    workouts.getAll.mockResolvedValue({
        data: [set({ rest_after_seconds: 0 })],
    } as never);
    renderDay();

    await waitFor(() => expect(workouts.getAll).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /rest 0:/i })).not.toBeInTheDocument();
});

it("shows the shortfall on a stopped tile", async () => {
    workouts.getAll.mockResolvedValue({
        data: [
            set({
                completed_at: `${DATE}T10:00:00`,
                reps: 5,
                completed_reps: 2,
                work_seconds: 40,
                actual_work_seconds: 85,
                ended_early: true,
            }),
        ],
    } as never);
    renderDay();

    // Target versus actual: 2 of 5 planned reps, and the Stop marked.
    expect(await screen.findByText(/2 \/ 5/)).toBeInTheDocument();
    expect(screen.getByText(/ended early/i)).toBeInTheDocument();
});

// --- The day player (plan 0018) ----------------------------------------------

it("counts only performed tiles as logged", async () => {
    workouts.getAll.mockResolvedValue({
        data: [
            set({ doc_id: 1, completed_at: `${DATE}T10:00:00`, order: 1 }),
            set({ doc_id: 2, exercise: "Farmer Carry", order: 2 }),
        ],
    } as never);
    renderDay();

    // Planned work is not logged work (plan 0018) — it reads as planned.
    expect(await screen.findByText(/1 exercise logged · 1 planned/)).toBeInTheDocument();
});

it("does not call a suggested tile logged", async () => {
    workouts.getAll.mockResolvedValue({ data: [set()] } as never);
    renderDay();

    expect(await screen.findByText(/0 exercises logged · 1 planned/)).toBeInTheDocument();
});

it("offers Play when the day has incomplete tiles, not when all are done", async () => {
    workouts.getAll.mockResolvedValue({
        data: [set({ completed_at: `${DATE}T10:00:00` })],
    } as never);
    renderDay();
    await waitFor(() => expect(workouts.getAll).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /^play$/i })).not.toBeInTheDocument();
});

it("opens the player on the first incomplete tile and locks it", async () => {
    workouts.getAll.mockResolvedValue({
        data: [
            set({ doc_id: 1, order: 1, work_seconds: 40, rest_seconds: 20 }),
            set({ doc_id: 2, order: 2, exercise: "Overhead Press" }),
        ],
    } as never);
    renderDay();

    await userEvent.click(await screen.findByRole("button", { name: /^play$/i }));

    // The hero counts down the get-ready against the first incomplete tile —
    // named in the hero as well as on its card.
    expect(await screen.findByText("GET READY")).toBeInTheDocument();
    expect(screen.getAllByText(/Weighted Pigeon Squat/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();

    // Every tile in the run is locked: no completion, mobility, delete or
    // edit — the buttons carry the lock title, and are disabled.
    const locked = screen.getAllByTitle(/locked while a run includes it/i);
    expect(locked.length).toBeGreaterThan(0);
    locked.forEach((button) => expect(button).toBeDisabled());
    expect(
        screen.getAllByRole("checkbox", { name: /mobility work/i })[0],
    ).toBeDisabled();
});

it("writes nothing when the run is stopped during get-ready", async () => {
    workouts.getAll.mockResolvedValue({
        data: [set({ work_seconds: 40 })],
    } as never);
    renderDay();

    await userEvent.click(await screen.findByRole("button", { name: /^play$/i }));
    await screen.findByText("GET READY");
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));

    await waitFor(() =>
        expect(workouts.perform).not.toHaveBeenCalled(),
    );
    expect(workouts.recordRestAfter).not.toHaveBeenCalled();
    // The run abandoned before any work is no result: back to the day.
    await waitFor(() =>
        expect(screen.getByRole("button", { name: /^play$/i })).toBeInTheDocument(),
    );
});

// --- Fake-timer player scenarios ---------------------------------------------
//
// The player runs on rAF deadlines, so these own the clock explicitly the
// way the hook's suite does, and clicks go through fireEvent: user-event's
// async internals wait on the very clock being faked.

const fakeClock = () => {
    vi.useFakeTimers({
        toFake: [
            "setTimeout",
            "clearTimeout",
            "setInterval",
            "clearInterval",
            "Date",
            "performance",
            "requestAnimationFrame",
            "cancelAnimationFrame",
        ],
    });
    return () => vi.useRealTimers();
};

const tick = (ms: number) => {
    act(() => {
        vi.advanceTimersByTime(ms);
    });
};

/** Drain the promises a save or a refetch resolves on, through the fake clock. */
const settle = async () => {
    for (let i = 0; i < 6; i++) {
        await act(async () => {
            vi.advanceTimersByTime(0);
            await Promise.resolve();
        });
    }
};

it("re-arms Play when a suggestion lands after a finished run", async () => {
    const restore = fakeClock();
    try {
        let stored: Workout[] = [
            set({ doc_id: 1, work_seconds: 5, reps: 1, rest_seconds: 0, rest_after_seconds: 0 }) as Workout,
        ];
        workouts.getAll.mockImplementation(
            (async () => ({ data: stored })) as never,
        );
        workouts.perform.mockImplementation((async (id: number) => {
            stored = stored.map((w) =>
                w.doc_id === id ? { ...w, completed_at: `${DATE}T11:00:00` } : w,
            );
            return { data: {} };
        }) as never);
        suggest.mockResolvedValue({ data: set({ doc_id: 9 }) } as never);

        renderDay();
        await settle();
        fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
        tick(5020); // get-ready
        tick(5100); // the single work rep
        await settle();

        expect(screen.getByText("DONE")).toBeInTheDocument();
        // Nothing incomplete: no Play, and no reset yet.
        expect(screen.queryByRole("button", { name: /^play$/i })).not.toBeInTheDocument();

        // The suggestion lands: the player re-arms and Play returns.
        stored = [
            ...stored,
            set({ doc_id: 9, exercise: "Deep Squat Hold", is_mobility: true, order: 2 }),
        ];
        fireEvent.click(screen.getByRole("button", { name: /movement break/i }));
        await settle();

        expect(screen.getByRole("button", { name: /^play$/i })).toBeInTheDocument();
        expect(screen.queryByText("DONE")).not.toBeInTheDocument();
    } finally {
        restore();
    }
});

it("locks every tile in the run, and the divider after a locked tile", async () => {
    const restore = fakeClock();
    try {
        workouts.getAll.mockResolvedValue({
            data: [
                set({ doc_id: 1, order: 1, work_seconds: 40, rest_seconds: 20, rest_after_seconds: 15 }),
                set({ doc_id: 2, order: 2, exercise: "Overhead Press", work_seconds: 30, reps: 1 }),
            ],
        } as never);
        renderDay();
        await settle();

        fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
        tick(5020);
        await settle();
        expect(screen.getByText("WORK")).toBeInTheDocument();

        // Every tile in the snapshot is locked, not only the one playing: a
        // queued tile deleted or ticked underneath the run is a 404 Retry
        // loop or a double count.
        const locks = screen.getAllByTitle(/locked while a run includes it/i);
        expect(locks.length).toBeGreaterThan(0);
        locks.forEach((button) => expect(button).toBeDisabled());

        // The divider after a locked tile has nowhere to go either.
        expect(screen.getByRole("button", { name: /rest 0:15/i })).toBeDisabled();
    } finally {
        restore();
    }
});

it("keeps the failed run's tiles locked in the error state", async () => {
    const restore = fakeClock();
    try {
        workouts.perform.mockRejectedValue(new Error("offline"));
        workouts.getAll.mockResolvedValue({
            data: [
                set({ doc_id: 1, order: 1, work_seconds: 5, reps: 1, rest_seconds: 0, rest_after_seconds: 15 }),
                set({ doc_id: 2, order: 2, exercise: "Overhead Press", work_seconds: 30, reps: 1 }),
            ],
        } as never);
        renderDay();
        await settle();

        fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
        tick(5020);
        tick(5100);
        await settle();

        expect(screen.getByRole("alert")).toBeInTheDocument();
        // A failed write is not a released snapshot: the tiles and the
        // divider stay locked until Retry lands or the run is discarded.
        const locks = screen.getAllByTitle(/locked while a run includes it/i);
        expect(locks.length).toBeGreaterThan(0);
        locks.forEach((button) => expect(button).toBeDisabled());
        expect(screen.getByRole("button", { name: /rest 0:15/i })).toBeDisabled();
    } finally {
        restore();
    }
});

it("closes an open delete confirm and edit form when Play starts", async () => {
    const restore = fakeClock();
    try {
        workouts.getAll.mockResolvedValue({
            data: [set({ doc_id: 1, work_seconds: 5, reps: 1 })],
        } as never);
        renderDay();
        await settle();

        // Open the two-step delete on the tile.
        const deleteButton = document.querySelector(".action-btn--danger");
        expect(deleteButton).not.toBeNull();
        fireEvent.click(deleteButton as Element);
        await settle();
        // The confirm step is visible.
        expect(screen.getByTitle(/confirm delete/i)).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
        await settle();

        // Play owns the snapshot now: nothing pre-opened may act under it.
        expect(screen.queryByTitle(/confirm delete/i)).not.toBeInTheDocument();
    } finally {
        restore();
    }
});

it("shows restart and skip beside pause on a timed run, and skip advances phases", async () => {
    const restore = fakeClock();
    try {
        workouts.getAll.mockResolvedValue({
            data: [set({ doc_id: 1, work_seconds: 40, reps: 2, rest_seconds: 20 })],
        } as never);
        renderDay();
        await settle();

        fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
        tick(5020);
        await settle();
        expect(screen.getByText("WORK")).toBeInTheDocument();

        expect(screen.getByRole("button", { name: "Restart timer" })).toBeEnabled();
        expect(screen.getByRole("button", { name: "Skip to next timer" })).toBeEnabled();

        // Skip ends the first rep early: the rest phase starts at once.
        fireEvent.click(screen.getByRole("button", { name: "Skip to next timer" }));
        await settle();
        expect(screen.getByText("REST")).toBeInTheDocument();

        // Restart re-arms the current phase at full.
        tick(5_000);
        fireEvent.click(screen.getByRole("button", { name: "Restart timer" }));
        await settle();
        expect(screen.getByRole("timer")).toHaveTextContent("0:20");
    } finally {
        restore();
    }
});

it("offers only Complete set on an untimed tile — no timers to restart or skip", async () => {
    const restore = fakeClock();
    try {
        workouts.getAll.mockResolvedValue({
            data: [set({ doc_id: 1, work_seconds: null, reps: 8 })],
        } as never);
        renderDay();
        await settle();

        fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
        tick(5020);
        await settle();

        expect(screen.getByRole("button", { name: "Complete set" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Restart timer" })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Skip to next timer" })).not.toBeInTheDocument();
    } finally {
        restore();
    }
});

it("cannot reach or fire the delete confirm on a locked tile", async () => {
    const restore = fakeClock();
    try {
        workouts.getAll.mockResolvedValue({
            data: [set({ doc_id: 1, work_seconds: 40 })],
        } as never);
        renderDay();
        await settle();

        fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
        tick(5020);
        await settle();
        expect(screen.getByText("WORK")).toBeInTheDocument();

        // The tile is in the run's snapshot, so it is locked: its delete is
        // disabled, which is what keeps `confirmingDelete` unset — the only
        // path to a Confirm is closed, and `delete` never fires.
        const deleteButton = document.querySelector(".action-btn--danger");
        expect(deleteButton).not.toBeNull();
        expect(deleteButton).toBeDisabled();
        fireEvent.click(deleteButton as Element);
        await settle();

        expect(screen.queryByTitle(/confirm delete/i)).not.toBeInTheDocument();
        expect(workouts.delete).not.toHaveBeenCalled();
        // And the tile is still there, planned, after the run.
        expect(screen.getByText("Weighted Pigeon Squat")).toBeInTheDocument();
    } finally {
        restore();
    }
});

it("closes an open edit form when Play starts", async () => {
    const restore = fakeClock();
    try {
        workouts.getAll.mockResolvedValue({
            data: [set({ doc_id: 1, work_seconds: 40 })],
        } as never);
        renderDay();
        await settle();

        // Open the tile's editor.
        fireEvent.click(screen.getByText("Weighted Pigeon Squat"));
        await settle();
        expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
        await settle();

        expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
    } finally {
        restore();
    }
});

it("offers a way out of a permanently failed write", async () => {
    const restore = fakeClock();
    try {
        workouts.perform.mockRejectedValue(new Error("offline"));
        workouts.getAll.mockResolvedValue({
            data: [set({ doc_id: 1, work_seconds: 5, reps: 1, rest_seconds: 0, rest_after_seconds: 0 })],
        } as never);
        renderDay();
        await settle();

        fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
        tick(5020);
        tick(5100);
        await settle();

        // The write failed: the run halts and says so, rather than claiming
        // the set reached the log.
        expect(screen.getByRole("alert")).toHaveTextContent(/not saved/i);

        fireEvent.click(screen.getByRole("button", { name: /discard/i }));
        await settle();

        // Back to a plain day: Play returns, and the tile's own actions are
        // no longer locked behind the failed run.
        expect(screen.getByRole("button", { name: /^play$/i })).toBeInTheDocument();
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    } finally {
        restore();
    }
});
