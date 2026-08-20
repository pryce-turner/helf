/**
 * The Food page had shipped, been type-checked, had its endpoints exercised
 * end-to-end — and had never been *mounted*. TypeScript cannot catch a hook
 * called conditionally, an undefined access inside a `.map`, or a chart that
 * throws on an empty series. This is the cheapest thing that can.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import FoodPage from "./Food";
import { foodApi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        foodApi: {
            getDay: vi.fn(),
            getSummary: vi.fn(),
            search: vi.fn(),
            create: vi.fn(),
            update: vi.fn(),
            log: vi.fn(),
            deleteLog: vi.fn(),
        },
    };
});

const mocked = vi.mocked(foodApi);

const day = (overrides: Record<string, unknown> = {}) => ({
    data: {
        date: "2026-08-10",
        totals: {
            date: "2026-08-10",
            kcal: 1850,
            protein_g: 140,
            carb_g: 180,
            fat_g: 60,
            entries: 3,
            foods_missing_macros: 0,
            supplements_taken: 0,
            kcal_target: 2730,
            ...(overrides.totals as object),
        },
        entries: (overrides.entries as unknown[]) ?? [],
    },
});

beforeEach(() => {
    vi.clearAllMocks();
    mocked.search.mockResolvedValue({ data: [] } as never);
});

describe("Food page", () => {
    it("renders intake against the measured target", async () => {
        mocked.getDay.mockResolvedValue(day() as never);
        renderPage(<FoodPage />, "/food");

        expect(await screen.findByText("1,850")).toBeInTheDocument();
        expect(screen.getByText("2,730")).toBeInTheDocument();
        expect(screen.getByText(/880 kcal left/)).toBeInTheDocument();
    });

    it("says how far over, not just that you are over", async () => {
        mocked.getDay.mockResolvedValue(
            day({ totals: { kcal: 3000 } }) as never,
        );
        renderPage(<FoodPage />, "/food");

        expect(await screen.findByText(/270 kcal over/)).toBeInTheDocument();
    });

    it("never invents a target when no scan has supplied one", async () => {
        mocked.getDay.mockResolvedValue(
            day({ totals: { kcal_target: null } }) as never,
        );
        renderPage(<FoodPage />, "/food");

        expect(
            await screen.findByText(/No target yet/),
        ).toBeInTheDocument();
        expect(screen.queryByText(/kcal left/)).not.toBeInTheDocument();
    });

    it("warns when the totals are understated", async () => {
        mocked.getDay.mockResolvedValue(
            day({ totals: { foods_missing_macros: 2 } }) as never,
        );
        renderPage(<FoodPage />, "/food");

        expect(
            await screen.findByText(/2 entries are missing macros/),
        ).toBeInTheDocument();
    });

    it("shows no supplements, even in a response that still carries them", async () => {
        mocked.getDay.mockResolvedValue(
            day({
                entries: [
                    {
                        doc_id: 1, consumed_at: "2026-08-10T08:00:00",
                        date: "2026-08-10", servings: 1, meal: "breakfast",
                        food_id: 1, name: "Oats", brand: "", kind: "food",
                        serving_desc: null, kcal: 300, protein_g: 10,
                        carb_g: 50, fat_g: 5,
                    },
                    {
                        doc_id: 2, consumed_at: "2026-08-10T07:00:00",
                        date: "2026-08-10", servings: 2, meal: null,
                        food_id: 2, name: "Omega-3", brand: "", kind: "supplement",
                        serving_desc: "1 softgel", kcal: null, protein_g: null,
                        carb_g: null, fat_g: null,
                    },
                ],
            }) as never,
        );
        renderPage(<FoodPage />, "/food");

        expect(await screen.findByText("breakfast")).toBeInTheDocument();
        // Supplements live on their own tab now. `/api/food/day` no longer
        // returns them at all, but the service worker serves /api network-first
        // and can hand back a day that predates the split - and a supplement
        // must not then appear as unfiled food.
        expect(screen.queryByText("supplements")).not.toBeInTheDocument();
        expect(screen.queryByText("unsorted")).not.toBeInTheDocument();
        expect(screen.queryByText("Omega-3")).not.toBeInTheDocument();
    });

    it("says an unlogged day is unlogged rather than showing zeros", async () => {
        mocked.getDay.mockResolvedValue(
            day({ totals: { kcal: null, protein_g: null } }) as never,
        );
        renderPage(<FoodPage />, "/food");

        expect(await screen.findByText("Nothing logged")).toBeInTheDocument();
    });

    it("opens the log form and offers only meals in the typeahead", async () => {
        const user = userEvent.setup();
        mocked.getDay.mockResolvedValue(day() as never);
        mocked.search.mockResolvedValue({
            data: [
                {
                    doc_id: 9, name: "Mango", brand: "", kind: "food",
                    serving_desc: null, kcal_per_serving: 60, protein_g: 1,
                    carb_g: 15, fat_g: 0, created_at: "2026-08-01",
                },
            ],
        } as never);

        renderPage(<FoodPage />, "/food");
        await user.click(await screen.findByRole("button", { name: /Log food/ }));
        await user.type(screen.getByLabelText("Food"), "man");

        await waitFor(() => expect(mocked.search).toHaveBeenCalled());
        // The third argument is the kind filter — without it the meal
        // typeahead offers magnesium.
        expect(mocked.search).toHaveBeenCalledWith("man", 50, "food");
    });

    /**
     * `food_log.date` is `substr(consumed_at, 1, 10)`, so the day an entry
     * lands on is whatever the first ten characters spell. `toISOString()`
     * spells the UTC date: west of Greenwich every evening meal was filed
     * under tomorrow and disappeared from the day it was logged on. A
     * screenshot cannot catch this — the request succeeds and the page
     * refetches a day that correctly no longer contains the entry.
     */
    it("logs against the viewed day, not the UTC one", async () => {
        const user = userEvent.setup();
        mocked.getDay.mockResolvedValue(day() as never);
        mocked.log.mockResolvedValue({ data: {} } as never);

        renderPage(<FoodPage />, "/food");
        await user.click(await screen.findByRole("button", { name: /Log food/ }));
        await user.type(screen.getByLabelText("Food"), "Rice");
        await user.click(screen.getByRole("button", { name: /Log it/ }));

        await waitFor(() => expect(mocked.log).toHaveBeenCalled());
        const sent = mocked.log.mock.calls[0][0] as { consumed_at: string };
        expect(sent.consumed_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/);
        expect(sent.consumed_at.slice(0, 10)).toBe(
            new Date().toLocaleDateString("en-CA"),
        );
    });
});
