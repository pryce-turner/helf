/**
 * The library (plan 0022): one list over your programs and blocks and the
 * built-in ones, and New program opening the builder.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import Library from "./Library";
import { libraryApi, programsApi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        libraryApi: { ...actual.libraryApi, get: vi.fn() },
        programsApi: { ...actual.programsApi, create: vi.fn() },
    };
});

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(libraryApi.get).mockResolvedValue({
        data: {
            programs: [
                { source: "mine", id: 4, name: "My split", built: true },
                { source: "builtin", key: "wendler_531", name: "Wendler 5/3/1", description: "Classic." },
            ],
            blocks: [
                { source: "mine", id: 1, name: "McGill Big 3", set_count: 15 },
                { source: "builtin", key: "press_core", name: "Press core", set_count: 4 },
            ],
        },
    } as never);
});

it("lists yours and the built-ins, labelled", async () => {
    renderPage(<Library />, "/library");

    expect(await screen.findByText("My split")).toBeInTheDocument();
    expect(screen.getByText("Built with the builder")).toBeInTheDocument();
    expect(screen.getByText("McGill Big 3")).toBeInTheDocument();
    expect(screen.getByText("15 sets")).toBeInTheDocument();
    expect(screen.getAllByText("Built-in")).toHaveLength(2);
});

it("creates a builder program on New program, named past yours", async () => {
    vi.mocked(programsApi.create).mockResolvedValue({ data: { doc_id: 9 } } as never);
    renderPage(<Library />, "/library");

    await userEvent.click(await screen.findByRole("button", { name: /new program/i }));
    await waitFor(() => expect(programsApi.create).toHaveBeenCalledTimes(1));
    const sent = vi.mocked(programsApi.create).mock.calls[0][0];
    expect(sent.name).toBe("New program");
    expect(sent.builder).toEqual({ weeks: 4, days: [{ name: "Day 1", items: [] }] });
    expect(sent.script).toContain("## Week 1 - Day 1");
});
