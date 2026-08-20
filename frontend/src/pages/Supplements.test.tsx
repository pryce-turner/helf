/**
 * Same reason as `Food.test.tsx`: shipped, type-checked, never mounted. This
 * page carries more state than any other — nested draft rows, a typeahead per
 * row, and an editor that doubles as the create form — which is exactly where
 * a render-time bug hides from `tsc`.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import Supplements from "./Supplements";
import { foodApi, stacksApi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        foodApi: {
            ...actual.foodApi,
            search: vi.fn(),
            getRecentLog: vi.fn(),
            deleteLog: vi.fn(),
        },
        stacksApi: {
            getAll: vi.fn(),
            create: vi.fn(),
            update: vi.fn(),
            delete: vi.fn(),
            log: vi.fn(),
        },
    };
});

const stacks = vi.mocked(stacksApi);
const foods = vi.mocked(foodApi);

const item = (id: number, name: string, servings: number, desc: string | null) => ({
    doc_id: id, food_id: id, name, brand: "", kind: "supplement" as const,
    serving_desc: desc, servings, order: id, kcal_per_serving: null,
});

const MORNING = {
    doc_id: 1,
    name: "Morning",
    note: null,
    order: 1,
    created_at: "2026-08-01",
    items: [
        item(1, "Omega-3", 2, "1 softgel, 1000mg EPA"),
        item(2, "Vitamin D3", 1, "1 tablet, 5000 IU"),
    ],
    taken_today: false,
    last_taken: "2026-08-08",
};

const dose = (id: number, name: string, at: string, servings: number) => ({
    doc_id: id,
    consumed_at: at,
    date: at.slice(0, 10),
    servings,
    meal: null,
    food_id: id,
    name,
    brand: "",
    kind: "supplement" as const,
    serving_desc: null,
    kcal: null,
    protein_g: null,
    carb_g: null,
    fat_g: null,
});

beforeEach(() => {
    vi.clearAllMocks();
    foods.search.mockResolvedValue({ data: [] } as never);
    foods.getRecentLog.mockResolvedValue({ data: [] } as never);
    foods.deleteLog.mockResolvedValue({ data: {} } as never);
});

describe("Supplements page", () => {
    it("renders a group with its doses", async () => {
        stacks.getAll.mockResolvedValue({ data: [MORNING] } as never);
        renderPage(<Supplements />, "/supplements");

        expect(await screen.findByText("Morning")).toBeInTheDocument();
        expect(screen.getByText("2 × 1 softgel, 1000mg EPA")).toBeInTheDocument();
        expect(screen.getByText("1 × 1 tablet, 5000 IU")).toBeInTheDocument();
    });

    it("shows when it was last taken, and a badge once it is", async () => {
        stacks.getAll.mockResolvedValue({ data: [MORNING] } as never);
        const { unmount } = renderPage(<Supplements />, "/supplements");
        expect(await screen.findByText(/Last taken/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Log all 2/ })).toBeInTheDocument();
        unmount();

        stacks.getAll.mockResolvedValue({
            data: [{ ...MORNING, taken_today: true }],
        } as never);
        renderPage(<Supplements />, "/supplements");

        expect(await screen.findByText("Taken today")).toBeInTheDocument();
        // Still loggable — taking it twice is a real thing that happens, and
        // the page should not pretend otherwise.
        expect(screen.getByRole("button", { name: "Log again" })).toBeInTheDocument();
        expect(screen.queryByText(/Last taken/)).not.toBeInTheDocument();
    });

    it("logs the whole group in one action", async () => {
        const user = userEvent.setup();
        stacks.getAll.mockResolvedValue({ data: [MORNING] } as never);
        stacks.log.mockResolvedValue({
            data: { stack: "Morning", consumed_at: "x", entries: [] },
        } as never);

        renderPage(<Supplements />, "/supplements");
        await user.click(await screen.findByRole("button", { name: /Log all 2/ }));

        await waitFor(() => expect(stacks.log).toHaveBeenCalledWith(1));
    });

    it("cannot log an empty group", async () => {
        stacks.getAll.mockResolvedValue({
            data: [{ ...MORNING, items: [] }],
        } as never);
        renderPage(<Supplements />, "/supplements");

        expect(await screen.findByText(/Nothing in this group yet/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Log all 0/ })).toBeDisabled();
    });

    it("creates a group with new supplements", async () => {
        const user = userEvent.setup();
        stacks.getAll.mockResolvedValue({ data: [] } as never);
        stacks.create.mockResolvedValue({ data: MORNING } as never);

        renderPage(<Supplements />, "/supplements");
        await user.click(await screen.findByRole("button", { name: /New group/ }));

        await user.type(screen.getByLabelText("Group name"), "Evening");
        await user.type(
            screen.getByPlaceholderText("Supplement name"),
            "Magnesium",
        );
        await user.type(
            screen.getByPlaceholderText("1 softgel, 1000mg"),
            "2 caps, 400mg",
        );
        await user.click(screen.getByRole("button", { name: "Create group" }));

        await waitFor(() =>
            expect(stacks.create).toHaveBeenCalledWith({
                name: "Evening",
                items: [
                    {
                        food: {
                            name: "Magnesium",
                            kind: "supplement",
                            serving_desc: "2 caps, 400mg",
                        },
                        servings: 1,
                    },
                ],
            }),
        );
    });

    it("reuses an existing supplement rather than making a near-duplicate", async () => {
        const user = userEvent.setup();
        stacks.getAll.mockResolvedValue({ data: [] } as never);
        stacks.create.mockResolvedValue({ data: MORNING } as never);
        foods.search.mockResolvedValue({
            data: [
                {
                    doc_id: 7, name: "Omega-3", brand: "", kind: "supplement",
                    serving_desc: "1 softgel, 1000mg EPA", kcal_per_serving: null,
                    protein_g: null, carb_g: null, fat_g: null,
                    created_at: "2026-08-01",
                },
            ],
        } as never);

        renderPage(<Supplements />, "/supplements");
        await user.click(await screen.findByRole("button", { name: /New group/ }));
        await user.type(screen.getByLabelText("Group name"), "Evening");
        await user.type(screen.getByPlaceholderText("Supplement name"), "ome");

        // Scoped to the typeahead: the catalog list below now renders an
        // "Edit Omega-3" button too, and an unscoped name match finds both.
        const suggestions = await screen.findByTestId("food-suggestions");
        await user.click(within(suggestions).getByRole("button", { name: /Omega-3/ }));
        await user.click(screen.getByRole("button", { name: "Create group" }));

        await waitFor(() =>
            expect(stacks.create).toHaveBeenCalledWith({
                name: "Evening",
                items: [{ food_id: 7, servings: 1 }],
            }),
        );
    });

    it("removing a row actually removes it, because items replace wholesale", async () => {
        const user = userEvent.setup();
        stacks.getAll.mockResolvedValue({ data: [MORNING] } as never);
        stacks.update.mockResolvedValue({ data: MORNING } as never);

        renderPage(<Supplements />, "/supplements");
        await user.click(await screen.findByRole("button", { name: "Edit Morning" }));
        await user.click(screen.getByRole("button", { name: "Remove Vitamin D3" }));
        await user.click(screen.getByRole("button", { name: "Save changes" }));

        await waitFor(() =>
            expect(stacks.update).toHaveBeenCalledWith(1, {
                name: "Morning",
                items: [{ food_id: 1, servings: 2 }],
            }),
        );
    });

    it("asks before deleting, and says history is kept", async () => {
        const user = userEvent.setup();
        stacks.getAll.mockResolvedValue({ data: [MORNING] } as never);
        stacks.delete.mockResolvedValue({ data: {} } as never);

        renderPage(<Supplements />, "/supplements");
        await user.click(await screen.findByRole("button", { name: "Delete Morning" }));

        expect(screen.getByText(/Past entries are kept/)).toBeInTheDocument();
        expect(stacks.delete).not.toHaveBeenCalled();

        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(stacks.delete).toHaveBeenCalledWith(1));
    });

    it("explains itself when there are no groups", async () => {
        stacks.getAll.mockResolvedValue({ data: [] } as never);
        renderPage(<Supplements />, "/supplements");

        const empty = await screen.findByText("No groups yet");
        expect(empty).toBeInTheDocument();
        expect(
            within(empty.parentElement!).getByText(/things you take together/),
        ).toBeInTheDocument();
    });

    it("lists what was actually swallowed, newest first", async () => {
        // The counterpart of the body page's measurement log. `taken_today`
        // answers "did I take it this morning"; this answers "what did I take",
        // and it reads across days because a dose filed against the wrong date
        // is invisible to any per-day view.
        stacks.getAll.mockResolvedValue({ data: [] } as never);
        foods.getRecentLog.mockResolvedValue({
            data: [
                dose(2, "Vitamin D3", "2026-08-09T07:02:00", 1),
                dose(1, "Omega-3", "2026-08-08T07:01:00", 2),
            ],
        } as never);
        renderPage(<Supplements />, "/supplements");

        await screen.findByText("Recent doses");
        expect(foods.getRecentLog).toHaveBeenCalledWith("supplement", 50);

        const rows = screen.getAllByRole("row").slice(1);
        expect(within(rows[0]).getByText("2026-08-09 07:02")).toBeInTheDocument();
        expect(within(rows[0]).getByText("Vitamin D3")).toBeInTheDocument();
        expect(within(rows[1]).getByText("×2")).toBeInTheDocument();
    });

    it("takes two taps to delete a dose", async () => {
        // Same rule as the measurement log: a native confirm() blocks the page
        // and cannot be dismissed, and two taps is harder to do by accident.
        stacks.getAll.mockResolvedValue({ data: [] } as never);
        foods.getRecentLog.mockResolvedValue({
            data: [dose(1, "Omega-3", "2026-08-08T07:01:00", 2)],
        } as never);
        const user = userEvent.setup();
        renderPage(<Supplements />, "/supplements");

        await user.click(await screen.findByRole("button", { name: /Delete Omega-3/ }));
        expect(foods.deleteLog).not.toHaveBeenCalled();

        await user.click(screen.getByRole("button", { name: /^Delete$/ }));
        await waitFor(() => expect(foods.deleteLog).toHaveBeenCalledWith(1));
    });

    it("says nothing at all when nothing has been logged", async () => {
        stacks.getAll.mockResolvedValue({ data: [] } as never);
        renderPage(<Supplements />, "/supplements");

        await screen.findByText(/No groups yet/);
        expect(screen.queryByText("Recent doses")).not.toBeInTheDocument();
    });
});
