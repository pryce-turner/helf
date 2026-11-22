/**
 * The Preset tab: the list, and Add creating one straight away (plan 0020).
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import Presets from "./Presets";
import { presetsApi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        presetsApi: { ...actual.presetsApi, getAll: vi.fn(), create: vi.fn() },
    };
});

const presets = vi.mocked(presetsApi);

const tile = (doc_id: number, exercise: string, order: number) => ({
    doc_id,
    preset_id: 1,
    order,
    exercise,
    category: "Legs",
    weight: null,
    weight_unit: "lbs",
    reps: 5,
    distance: null,
    distance_unit: null,
    comment: null,
    is_mobility: false,
    work_seconds: null,
    rest_seconds: null,
    rest_after_seconds: null,
});

beforeEach(() => {
    vi.clearAllMocks();
});

it("lists each preset with its set count and movements, in order", async () => {
    presets.getAll.mockResolvedValue({
        data: [
            {
                doc_id: 1,
                name: "Leg day",
                created_at: "2026-11-22",
                updated_at: "2026-11-22",
                items: [tile(2, "Lunge", 3), tile(1, "Squat", 1), tile(3, "Squat", 2)],
            },
        ],
    } as never);
    renderPage(<Presets />, "/presets");

    expect(await screen.findByText("Leg day")).toBeInTheDocument();
    expect(screen.getByText("3 sets · Squat, Lunge")).toBeInTheDocument();
});

it("says what a preset is for when there are none", async () => {
    presets.getAll.mockResolvedValue({ data: [] } as never);
    renderPage(<Presets />, "/presets");

    expect(await screen.findByText("No presets yet")).toBeInTheDocument();
});

it("creates a preset on Add and opens it", async () => {
    presets.getAll.mockResolvedValue({ data: [] } as never);
    presets.create.mockResolvedValue({
        data: { doc_id: 9, name: "New preset", created_at: "", updated_at: "", items: [] },
    } as never);
    renderPage(<Presets />, "/presets");

    await userEvent.click((await screen.findAllByRole("button", { name: /add preset/i }))[0]);

    await waitFor(() => expect(presets.create).toHaveBeenCalledTimes(1));
    // Navigated away: the list is no longer mounted.
    await waitFor(() => expect(screen.queryByText("No presets yet")).not.toBeInTheDocument());
});
