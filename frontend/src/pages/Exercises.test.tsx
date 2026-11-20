/**
 * The exercise catalog's three editable judgements: which category a movement
 * belongs to, how good it is, and whether it is also mobility work.
 *
 * Rating and mobility save on the spot rather than behind Edit/Save, so the
 * request each control makes *is* the feature — and the rating's is the subtle
 * one, because clearing sends an explicit null that an `is not None` guard on
 * the server would silently drop.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import ExercisesPage from "./Exercises";
import { categoriesApi, exercisesApi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
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
    };
});

const mockedExercises = vi.mocked(exercisesApi);
const mockedCategories = vi.mocked(categoriesApi);

const exercise = (overrides: Record<string, unknown> = {}) => ({
    doc_id: 1,
    name: "Plate Rollup",
    category: "Arms",
    form: null,
    application: null,
    rating: null,
    movement_break_enabled: false,
    reps_enabled: true,
    default_reps: null,
    weight_enabled: true,
    default_weight_lb: null,
    distance_enabled: false,
    default_distance: null,
    default_distance_unit: null,
    time_enabled: false,
    default_work_seconds: null,
    default_rest_seconds: null,
    default_rest_after_seconds: null,
    last_used: "2026-07-08",
    use_count: 12,
    created_at: "2026-01-01",
    ...overrides,
});

beforeEach(() => {
    vi.clearAllMocks();
    mockedExercises.getAll.mockResolvedValue({ data: [exercise()] } as never);
    mockedExercises.update.mockResolvedValue({ data: exercise() } as never);
    mockedCategories.getAll.mockResolvedValue({
        data: [
            { doc_id: 1, name: "Arms", created_at: "2026-01-01" },
            { doc_id: 2, name: "Legs", created_at: "2026-01-01" },
        ],
    } as never);
});

/** Categories collapse by default; the controls live inside one. */
const openCategory = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(await screen.findByRole("button", { name: /ARMS/ }));
};

describe("Exercises: rating", () => {
    it("rates a movement on the spot", async () => {
        const user = userEvent.setup();
        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);

        await user.click(
            await screen.findByRole("button", { name: "Rate Plate Rollup 4 of 5" }),
        );

        await waitFor(() =>
            expect(mockedExercises.update).toHaveBeenCalledWith(1, { rating: 4 }),
        );
    });

    it("clears a rating by clicking the star it already sits on", async () => {
        const user = userEvent.setup();
        mockedExercises.getAll.mockResolvedValue({
            data: [exercise({ rating: 4 })],
        } as never);

        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);

        // Same star, now labelled as the way out rather than a rating.
        await user.click(
            await screen.findByRole("button", {
                name: "Clear the rating for Plate Rollup",
            }),
        );

        // Explicitly null, not omitted: absence means "leave alone".
        await waitFor(() =>
            expect(mockedExercises.update).toHaveBeenCalledWith(1, { rating: null }),
        );
    });

    it("shows unrated as no stars rather than one", async () => {
        const user = userEvent.setup();
        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);

        const stars = await screen.findAllByRole("button", {
            name: /Rate Plate Rollup/,
        });
        expect(stars).toHaveLength(5);
        stars.forEach((star) =>
            expect(star).toHaveAttribute("aria-pressed", "false"),
        );
    });
});

describe("Exercises: mobility is not a property of the movement", () => {
    it("offers no mobility control, because the objective decides it", async () => {
        const user = userEvent.setup();
        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);

        // The flag moved to the set (d7e4f2a91b83). A good morning is a loaded
        // hinge in one session and a loaded stretch in the next, so a checkbox
        // here would force one answer onto both — and re-checking it would
        // silently reinterpret every set of that movement ever logged.
        await screen.findByRole("heading", { name: /Plate Rollup/ });
        expect(
            screen.queryByRole("checkbox", { name: /Mobility/ }),
        ).not.toBeInTheDocument();
        expect(screen.queryByText("Mobility")).not.toBeInTheDocument();
    });
});

describe("Exercises: choosing a category", () => {
    it("offers the existing categories rather than a blank field", async () => {
        const user = userEvent.setup();
        renderPage(<ExercisesPage />, "/exercises");

        await user.click(await screen.findByRole("button", { name: /Add Exercise/ }));
        await user.click(screen.getByRole("combobox"));

        expect(
            await screen.findByRole("option", { name: "Arms" }),
        ).toBeInTheDocument();
        expect(screen.getByRole("option", { name: "Legs" })).toBeInTheDocument();
        // Creating one stays possible — a list you cannot add to is worse than
        // a typo — but it is the last item rather than the default.
        expect(
            screen.getByRole("option", { name: /New category/ }),
        ).toBeInTheDocument();
    });

    it("switches to a text field when a new category is wanted", async () => {
        const user = userEvent.setup();
        renderPage(<ExercisesPage />, "/exercises");

        await user.click(await screen.findByRole("button", { name: /Add Exercise/ }));
        await user.click(screen.getByRole("combobox"));
        await user.click(await screen.findByRole("option", { name: /New category/ }));

        const field = await screen.findByPlaceholderText("New category name");
        await user.type(field, "Forearms");
        expect(field).toHaveValue("Forearms");
    });
});

describe("Exercises: form and application", () => {
    it("shows them as two separate blocks", async () => {
        const user = userEvent.setup();
        mockedExercises.getAll.mockResolvedValue({
            data: [
                exercise({
                    form: "hold the brace, ribs down",
                    application: "second set fades to load too high to drop 5lb",
                }),
            ],
        } as never);

        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);

        expect(await screen.findByText("hold the brace, ribs down")).toBeInTheDocument();
        expect(
            screen.getByText("second set fades to load too high to drop 5lb"),
        ).toBeInTheDocument();
    });

    it("edits application without restating form", async () => {
        const user = userEvent.setup();
        mockedExercises.getAll.mockResolvedValue({
            data: [exercise({ form: "hold the brace", application: "old read" })],
        } as never);

        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);
        await user.click(await screen.findByRole("button", { name: /edit/i }));

        const application = screen.getByLabelText("Application");
        await user.clear(application);
        await user.type(application, "new read");
        await user.click(screen.getByRole("button", { name: /save/i }));

        // The whole point of the split: form goes back unchanged, and the
        // caller never had to retype it.
        await waitFor(() =>
            expect(mockedExercises.update).toHaveBeenCalledWith(
                1,
                expect.objectContaining({
                    form: "hold the brace",
                    application: "new read",
                }),
            ),
        );
    });
});

describe("Exercises: the movement break pool", () => {
    it("puts a movement in the pool, with a default bout", async () => {
        const user = userEvent.setup();
        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);

        await user.click(
            await screen.findByRole("button", {
                name: "Add Plate Rollup to movement breaks",
            }),
        );

        // A pool member is timed by definition, so joining seeds the default
        // bout the old one-column pool carried.
        await waitFor(() =>
            expect(mockedExercises.update).toHaveBeenCalledWith(1, {
                movement_break_enabled: true,
                time_enabled: true,
                default_work_seconds: 30,
            }),
        );
    });

    it("keeps a movement's own bout when it joins the pool", async () => {
        const user = userEvent.setup();
        mockedExercises.getAll.mockResolvedValue({
            data: [
                exercise({
                    time_enabled: true,
                    default_work_seconds: 45,
                }),
            ],
        } as never);
        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);

        await user.click(
            await screen.findByRole("button", {
                name: "Add Plate Rollup to movement breaks",
            }),
        );

        await waitFor(() =>
            expect(mockedExercises.update).toHaveBeenCalledWith(1, {
                movement_break_enabled: true,
                time_enabled: true,
                default_work_seconds: 45,
            }),
        );
    });

    it("takes a movement out of the pool", async () => {
        const user = userEvent.setup();
        mockedExercises.getAll.mockResolvedValue({
            data: [
                exercise({
                    movement_break_enabled: true,
                    time_enabled: true,
                    default_work_seconds: 40,
                }),
            ],
        } as never);
        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);

        // The button carries the bout, so the pool's state is visible without
        // opening the editor.
        const toggle = await screen.findByRole("button", {
            name: "Remove Plate Rollup from movement breaks",
        });
        expect(toggle).toHaveTextContent("40s");

        await user.click(toggle);

        await waitFor(() =>
            expect(mockedExercises.update).toHaveBeenCalledWith(1, {
                movement_break_enabled: false,
            }),
        );
    });
});

describe("Exercises: set tile field configuration", () => {
    it("shows the four groups with their current configuration", async () => {
        const user = userEvent.setup();
        // Farmer Carry: Reps, Weight and Time on, the load filled in on the
        // day rather than defaulted.
        mockedExercises.getAll.mockResolvedValue({
            data: [
                exercise({
                    name: "Farmer Carry",
                    time_enabled: true,
                    default_work_seconds: 40,
                    default_rest_seconds: 20,
                    default_rest_after_seconds: 15,
                    movement_break_enabled: true,
                }),
            ],
        } as never);
        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);
        await user.click(await screen.findByRole("button", { name: /edit/i }));

        expect(screen.getByRole("checkbox", { name: "Reps" })).toBeChecked();
        expect(screen.getByRole("checkbox", { name: "Weight" })).toBeChecked();
        expect(screen.getByRole("checkbox", { name: "Distance" })).not.toBeChecked();
        expect(screen.getByRole("checkbox", { name: "Time" })).toBeChecked();
        // Weight is enabled but defaulted blank — filled in on the day tile.
        expect(screen.getByLabelText("Default weight")).toHaveValue(null);
        expect(screen.getByLabelText("Work seconds")).toHaveValue(40);
        expect(screen.getByLabelText("Rest seconds")).toHaveValue(20);
        expect(screen.getByLabelText("Rest after set seconds")).toHaveValue(15);
    });

    it("hides a group's defaults while it is disabled, without losing them", async () => {
        const user = userEvent.setup();
        mockedExercises.getAll.mockResolvedValue({
            data: [
                exercise({
                    time_enabled: true,
                    default_work_seconds: 40,
                }),
            ],
        } as never);
        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);
        await user.click(await screen.findByRole("button", { name: /edit/i }));

        await user.click(screen.getByRole("checkbox", { name: "Time" }));
        expect(screen.queryByLabelText("Work seconds")).not.toBeInTheDocument();

        await user.click(screen.getByRole("checkbox", { name: "Time" }));
        expect(screen.getByLabelText("Work seconds")).toHaveValue(40);
    });

    it("saves the whole configuration, blanks becoming explicit nulls", async () => {
        const user = userEvent.setup();
        renderPage(<ExercisesPage />, "/exercises");
        await openCategory(user);
        await user.click(await screen.findByRole("button", { name: /edit/i }));

        await user.click(screen.getByRole("checkbox", { name: "Time" }));
        await user.type(screen.getByLabelText("Work seconds"), "40");
        await user.type(screen.getByLabelText("Rest seconds"), "20");
        await user.click(screen.getByRole("button", { name: /save/i }));

        await waitFor(() =>
            expect(mockedExercises.update).toHaveBeenCalledWith(
                1,
                expect.objectContaining({
                    time_enabled: true,
                    default_work_seconds: 40,
                    default_rest_seconds: 20,
                    default_rest_after_seconds: null,
                    reps_enabled: true,
                    weight_enabled: true,
                    distance_enabled: false,
                }),
            ),
        );
    });
});
