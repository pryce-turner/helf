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
    notes: null,
    rating: null,
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
