/**
 * A preset on the day editor (plan 0020).
 *
 * The editor is the day's own, fed a preset instead of a date. What is worth
 * pinning is the seam: tiles go to the preset's store without a date, the
 * day-only controls (completion, Play, Move, Copy) are absent, and Apply puts
 * the tiles on the chosen day.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { format } from "date-fns";
import { beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import PresetEditor from "./PresetEditor";
import { categoriesApi, exercisesApi, presetsApi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        presetsApi: {
            getAll: vi.fn(),
            getById: vi.fn(),
            create: vi.fn(),
            rename: vi.fn(),
            delete: vi.fn(),
            addItem: vi.fn(),
            updateItem: vi.fn(),
            deleteItem: vi.fn(),
            reorder: vi.fn(),
            apply: vi.fn(),
        },
        exercisesApi: {
            ...actual.exercisesApi,
            getAll: vi.fn(),
            getRecent: vi.fn(),
            getMovementBreaks: vi.fn(),
        },
        categoriesApi: { ...actual.categoriesApi, getAll: vi.fn() },
    };
});

const presets = vi.mocked(presetsApi);

const item = (overrides: Record<string, unknown> = {}) => ({
    doc_id: 11,
    preset_id: 3,
    order: 1,
    exercise: "Barbell Squat",
    category: "Legs",
    weight: 185,
    weight_unit: "lbs",
    reps: 5,
    distance: null,
    distance_unit: null,
    comment: null,
    is_mobility: false,
    work_seconds: null,
    rest_seconds: null,
    rest_after_seconds: null,
    ...overrides,
});

const preset = (items = [item()]) => ({
    doc_id: 3,
    name: "Leg day",
    created_at: "2026-11-22T10:00:00",
    updated_at: "2026-11-22T10:00:00",
    items,
});

const renderEditor = () => renderPage(<PresetEditor />, "/presets/3", "/presets/:id");

beforeEach(() => {
    vi.clearAllMocks();
    presets.getById.mockResolvedValue({ data: preset() } as never);
    vi.mocked(exercisesApi).getAll.mockResolvedValue({
        data: [
            {
                doc_id: 1,
                name: "Barbell Squat",
                category: "Legs",
                reps_enabled: true,
                default_reps: 5,
                weight_enabled: true,
                default_weight_lb: 135,
                distance_enabled: false,
                default_distance: null,
                default_distance_unit: null,
                time_enabled: false,
                default_work_seconds: null,
                default_rest_seconds: null,
                default_rest_after_seconds: null,
                movement_break_enabled: false,
            },
        ],
    } as never);
    vi.mocked(exercisesApi).getRecent.mockResolvedValue({ data: [] } as never);
    vi.mocked(exercisesApi).getMovementBreaks.mockResolvedValue({ data: [] } as never);
    vi.mocked(categoriesApi).getAll.mockResolvedValue({
        data: [{ doc_id: 1, name: "Legs", created_at: "2026-01-01" }],
    } as never);
});

it("shows the preset's tiles without the day-only controls", async () => {
    renderEditor();

    expect(await screen.findByText("Barbell Squat")).toBeInTheDocument();
    expect(screen.getByText("Leg day")).toBeInTheDocument();
    expect(screen.getByText("1 set")).toBeInTheDocument();
    // A preset is never performed: no tick, no player, nothing to move.
    expect(screen.queryByTitle(/mark complete/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /play/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^move$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^copy$/i })).not.toBeInTheDocument();
    // Whether a set is mobility work is planned, so it stays.
    expect(screen.getByRole("checkbox", { name: /mobility work/i })).toBeInTheDocument();
});

it("adds a set to the preset, with no date", async () => {
    presets.addItem.mockResolvedValue({ data: item({ doc_id: 12, order: 2 }) } as never);
    renderEditor();

    await userEvent.click(await screen.findByRole("button", { name: /^add$/i }));
    await userEvent.type(screen.getByRole("combobox", { name: "Search exercises" }), "squa");
    await userEvent.click(await screen.findByRole("option", { name: /Barbell Squat/ }));
    await userEvent.click(screen.getByRole("button", { name: /add workout/i }));

    await waitFor(() => expect(presets.addItem).toHaveBeenCalledTimes(1));
    const [presetId, sent] = presets.addItem.mock.calls[0];
    expect(presetId).toBe(3);
    expect(sent).toMatchObject({ exercise: "Barbell Squat", category: "Legs", reps: 5, weight: 135 });
    expect(sent).not.toHaveProperty("date");
});

it("edits a tile through the preset's store", async () => {
    presets.updateItem.mockResolvedValue({ data: item({ reps: 3 }) } as never);
    renderEditor();

    await userEvent.click(await screen.findByText("Barbell Squat"));
    const reps = await screen.findByLabelText("Reps");
    await userEvent.clear(reps);
    await userEvent.type(reps, "3");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
        expect(presets.updateItem).toHaveBeenCalledWith(11, expect.objectContaining({ reps: 3 })),
    );
});

it("applies the preset to the chosen day", async () => {
    presets.apply.mockResolvedValue({
        data: { preset_id: 3, date: "x", count: 1, message: "ok" },
    } as never);
    renderEditor();

    await userEvent.click(await screen.findByRole("button", { name: /apply to day/i }));
    const today = format(new Date(), "yyyy-MM-dd");
    await userEvent.click(
        screen.getByRole("button", { name: `Apply to ${format(new Date(), "MMM d, yyyy")}` }),
    );

    await waitFor(() => expect(presets.apply).toHaveBeenCalledWith(3, today));
});

it("offers no apply for an empty preset", async () => {
    presets.getById.mockResolvedValue({ data: preset([]) } as never);
    renderEditor();

    expect(await screen.findByText("No sets yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply to day/i })).not.toBeInTheDocument();
});

it("renames the preset", async () => {
    presets.rename.mockResolvedValue({ data: { ...preset(), name: "Legs A" } } as never);
    renderEditor();

    await userEvent.click(await screen.findByRole("button", { name: /rename preset/i }));
    const field = screen.getByLabelText("Preset name");
    await userEvent.clear(field);
    await userEvent.type(field, "Legs A{Enter}");

    await waitFor(() => expect(presets.rename).toHaveBeenCalledWith(3, "Legs A"));
});

it("will not save a blank name", async () => {
    renderEditor();

    await userEvent.click(await screen.findByRole("button", { name: /rename preset/i }));
    const field = screen.getByLabelText("Preset name");
    await userEvent.clear(field);
    await userEvent.type(field, "{Enter}");

    expect(await screen.findByText("A preset needs a name")).toBeInTheDocument();
    expect(presets.rename).not.toHaveBeenCalled();
});

it("takes two taps to delete the preset", async () => {
    presets.delete.mockResolvedValue({} as never);
    renderEditor();

    await userEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    expect(presets.delete).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /delete preset/i }));

    await waitFor(() => expect(presets.delete).toHaveBeenCalledWith(3));
});

it("totals the timed work beside the set count", async () => {
    presets.getById.mockResolvedValue({
        data: preset([
            item({ doc_id: 1, reps: 6, work_seconds: 10, rest_seconds: 5 }),
            item({ doc_id: 2, order: 2, reps: 4, work_seconds: 10 }),
            item({ doc_id: 3, order: 3, reps: 5 }),
        ]),
    } as never);
    renderEditor();

    expect(await screen.findByText("3 sets · 1:40 timed")).toBeInTheDocument();
});
