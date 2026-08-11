/**
 * "Include upcoming workouts" was a checkbox that did nothing.
 *
 * Not because it was unwired — the flag reaches the query key and the request
 * — but because an estimated 1RM is `(0.033 x reps x weight) + weight`, so
 * `progression_service` drops a planned set that carries no weight. Every
 * upcoming row in this database is rep-only, so the filtered list came back
 * empty whichever way the box was ticked, for every exercise, silently.
 *
 * The live data only exercises the empty case, so the enabled path is only
 * ever covered here.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import ProgressionPage from "./Progression";
import { progressionApi, upcomingApi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        progressionApi: {
            getByExercise: vi.fn(),
            getMainLifts: vi.fn(),
            getExerciseList: vi.fn(),
        },
        upcomingApi: { getAll: vi.fn() },
    };
});

const mockedProgression = vi.mocked(progressionApi);
const mockedUpcoming = vi.mocked(upcomingApi);

const planned = (overrides: Record<string, unknown> = {}) => ({
    doc_id: 1,
    session: 7,
    exercise: "Barbell Squat",
    category: "Legs",
    weight: null,
    weight_unit: "lbs",
    reps: 5,
    distance: null,
    distance_unit: null,
    time: null,
    comment: null,
    created_at: "2026-03-31",
    ...overrides,
});

beforeEach(() => {
    vi.clearAllMocks();
    mockedProgression.getExerciseList.mockResolvedValue({
        data: ["Barbell Squat"],
    } as never);
    mockedProgression.getByExercise.mockResolvedValue({
        data: {
            exercise: "Barbell Squat",
            historical: [
                {
                    date: "2026-07-08",
                    weight: 225,
                    weight_unit: "lbs",
                    reps: 5,
                    estimated_1rm: 262.1,
                    comment: null,
                },
            ],
            upcoming: [],
        },
    } as never);
});

describe("Progression: including upcoming workouts", () => {
    it("says the planned sets carry no weight rather than toggling nothing", async () => {
        mockedUpcoming.getAll.mockResolvedValue({
            data: [planned(), planned({ doc_id: 2 })],
        } as never);

        renderPage(<ProgressionPage />, "/progression");

        const box = await screen.findByLabelText(/Include upcoming workouts/);
        await waitFor(() => expect(box).toBeDisabled());
        expect(box).not.toBeChecked();
        expect(
            screen.getByText(/2 planned sets have no weight/),
        ).toBeInTheDocument();
    });

    it("distinguishes nothing planned from planned-without-weight", async () => {
        mockedUpcoming.getAll.mockResolvedValue({
            data: [planned({ exercise: "Decline Crunch" })],
        } as never);

        renderPage(<ProgressionPage />, "/progression");

        const box = await screen.findByLabelText(/Include upcoming workouts/);
        await waitFor(() => expect(box).toBeDisabled());
        expect(
            screen.getByText(/nothing planned for this exercise/),
        ).toBeInTheDocument();
    });

    it("stays usable when a planned set does carry a weight", async () => {
        const user = userEvent.setup();
        mockedUpcoming.getAll.mockResolvedValue({
            data: [planned({ weight: 245 })],
        } as never);

        renderPage(<ProgressionPage />, "/progression");

        const box = await screen.findByLabelText(/Include upcoming workouts/);
        await waitFor(() => expect(box).toBeEnabled());
        expect(box).toBeChecked();

        // Unticking has to reach the request — that is the whole point of the
        // control, and the query key carries the flag.
        await user.click(box);
        await waitFor(() =>
            expect(mockedProgression.getByExercise).toHaveBeenCalledWith(
                "Barbell Squat",
                false,
            ),
        );
    });
});
