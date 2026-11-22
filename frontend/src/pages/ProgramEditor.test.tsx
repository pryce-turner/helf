/**
 * A program of yours (plan 0022): the builder when the builder wrote it, the
 * script editor otherwise - and "Edit as script" detaching one from the other.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import ProgramEditor from "./ProgramEditor";
import { exercisesApi, libraryApi, programsApi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        libraryApi: { ...actual.libraryApi, get: vi.fn(), check: vi.fn() },
        programsApi: { ...actual.programsApi, getById: vi.fn(), update: vi.fn(), delete: vi.fn() },
        exercisesApi: { ...actual.exercisesApi, getAll: vi.fn() },
    };
});

const program = (overrides: Record<string, unknown> = {}) => ({
    doc_id: 4,
    name: "My split",
    script: "## Press\n",
    builder: { weeks: 1, days: [{ name: "Press", items: [] }] },
    created_at: "2026-11-22",
    updated_at: "2026-11-22",
    ...overrides,
});

const renderEditor = () => renderPage(<ProgramEditor />, "/library/programs/4", "/library/programs/:id");

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(programsApi.getById).mockResolvedValue({ data: program() } as never);
    vi.mocked(programsApi.update).mockResolvedValue({ data: program() } as never);
    vi.mocked(libraryApi.check).mockResolvedValue({ data: { sets: 3, sessions: 1, mobility_sets: 0 } } as never);
    vi.mocked(libraryApi.get).mockResolvedValue({
        data: { programs: [], blocks: [{ source: "builtin", key: "press_core", name: "Press core", set_count: 4 }] },
    } as never);
    vi.mocked(exercisesApi.getAll).mockResolvedValue({ data: [] } as never);
});

it("builds a day from a block and a line, and saves the script with its model", async () => {
    renderEditor();

    await userEvent.click(await screen.findByRole("button", { name: "Block" }));
    await userEvent.selectOptions(screen.getByLabelText("Block"), "Press core");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    await userEvent.click(screen.getByRole("button", { name: "Line" }));
    await userEvent.type(screen.getByLabelText("Script line"), "Pull Up / 3x8");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(screen.getByText("[Press core]")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(programsApi.update).toHaveBeenCalledTimes(1));
    const [id, changes] = vi.mocked(programsApi.update).mock.calls[0];
    expect(id).toBe(4);
    expect(changes.script).toContain("## Press\n[Press core]\nPull Up / 3x8");
    expect(changes.builder?.days[0].items).toEqual([
        { kind: "block", name: "Press core" },
        { kind: "line", text: "Pull Up / 3x8" },
    ]);
});

it("shows the server's check of the script as you build", async () => {
    vi.mocked(libraryApi.check).mockRejectedValue({ response: { data: { detail: "there is no block named 'X'" } } });
    renderEditor();
    expect(await screen.findByText("there is no block named 'X'", {}, { timeout: 2000 })).toBeInTheDocument();
});

it("takes two taps to leave the builder, then saves the script alone", async () => {
    renderEditor();

    await userEvent.click(await screen.findByRole("button", { name: /^edit as script$/i }));
    expect(programsApi.update).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /leaves the builder/i }));

    await waitFor(() => expect(programsApi.update).toHaveBeenCalledTimes(1));
    expect(vi.mocked(programsApi.update).mock.calls[0][1]).not.toHaveProperty("builder");
});

it("opens a hand-written program in the script editor", async () => {
    vi.mocked(programsApi.getById).mockResolvedValue({
        data: program({ builder: null, script: "## A\nPlank / 1x1 30s\n" }),
    } as never);
    renderEditor();

    const editor = await screen.findByRole("textbox");
    expect(editor).toHaveValue("## A\nPlank / 1x1 30s\n");
    await userEvent.type(editor, "x");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
        expect(programsApi.update).toHaveBeenCalledWith(4, { script: "## A\nPlank / 1x1 30s\nx" }),
    );
});
