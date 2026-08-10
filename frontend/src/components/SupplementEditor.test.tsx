import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import SupplementEditor from "./SupplementEditor";
import { foodApi } from "@/lib/api";
import type { Food } from "@/types/food";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        foodApi: { ...actual.foodApi, usage: vi.fn(), update: vi.fn() },
    };
});

const mocked = vi.mocked(foodApi);

const OMEGA: Food = {
    doc_id: 4,
    name: "Omega-3",
    brand: "",
    kind: "supplement",
    serving_desc: "1 softgel, 1000mg EPA",
    kcal_per_serving: 10,
    protein_g: null,
    carb_g: null,
    fat_g: 1,
    created_at: "2026-08-01",
};

const usage = (over: Record<string, unknown> = {}) => ({
    data: {
        food_id: 4,
        entries: 47,
        first_logged: "2026-03-01",
        last_logged: "2026-08-10",
        stacks: ["Morning", "Evening"],
        ...over,
    },
});

beforeEach(() => {
    vi.clearAllMocks();
    mocked.usage.mockResolvedValue(usage() as never);
    mocked.update.mockResolvedValue({ data: OMEGA } as never);
});

describe("SupplementEditor", () => {
    it("loads the current values", async () => {
        renderPage(<SupplementEditor food={OMEGA} onDone={() => {}} />);

        expect(await screen.findByLabelText("Name")).toHaveValue("Omega-3");
        expect(screen.getByLabelText("Serving")).toHaveValue("1 softgel, 1000mg EPA");
        expect(screen.getByLabelText("kcal / serving")).toHaveValue(10);
        // A macro nobody has filled in is empty, not 0 — unknown and zero are
        // different facts, and `foods_missing_macros` counts on the difference.
        expect(screen.getByLabelText("protein g")).toHaveValue(null);
    });

    it("says which groups use it", async () => {
        renderPage(<SupplementEditor food={OMEGA} onDone={() => {}} />);
        expect(await screen.findByText("In Morning, Evening.")).toBeInTheDocument();
    });

    it("warns how much history a macro change rewrites", async () => {
        const user = userEvent.setup();
        renderPage(<SupplementEditor food={OMEGA} onDone={() => {}} />);
        await screen.findByLabelText("kcal / serving");

        await user.clear(screen.getByLabelText("kcal / serving"));
        await user.type(screen.getByLabelText("kcal / serving"), "12");

        const warning = await screen.findByText(/rewrites/);
        expect(warning).toHaveTextContent("47");
        expect(warning).toHaveTextContent("1 Mar 2026");
    });

    it("does not warn when only the serving text changed", async () => {
        const user = userEvent.setup();
        renderPage(<SupplementEditor food={OMEGA} onDone={() => {}} />);
        await screen.findByLabelText("Serving");

        await user.clear(screen.getByLabelText("Serving"));
        await user.type(screen.getByLabelText("Serving"), "1 softgel, 1200mg EPA");

        // A warning that fires on every edit is a warning nobody reads.
        expect(screen.queryByText(/rewrites/)).not.toBeInTheDocument();
    });

    it("does not warn when there is no history to rewrite", async () => {
        const user = userEvent.setup();
        mocked.usage.mockResolvedValue(usage({ entries: 0, first_logged: null }) as never);
        renderPage(<SupplementEditor food={OMEGA} onDone={() => {}} />);
        await screen.findByLabelText("kcal / serving");

        await user.clear(screen.getByLabelText("kcal / serving"));
        await user.type(screen.getByLabelText("kcal / serving"), "12");

        expect(screen.queryByText(/rewrites/)).not.toBeInTheDocument();
    });

    it("saves, sending an emptied macro as null rather than zero", async () => {
        const user = userEvent.setup();
        const onDone = vi.fn();
        renderPage(<SupplementEditor food={OMEGA} onDone={onDone} />);
        await screen.findByLabelText("Serving");

        await user.clear(screen.getByLabelText("Serving"));
        await user.type(screen.getByLabelText("Serving"), "1 softgel, 1200mg EPA");
        await user.clear(screen.getByLabelText("fat g"));
        await user.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() =>
            expect(mocked.update).toHaveBeenCalledWith(4, {
                name: "Omega-3",
                brand: "",
                serving_desc: "1 softgel, 1200mg EPA",
                kcal_per_serving: 10,
                protein_g: null,
                carb_g: null,
                fat_g: null,
            }),
        );
        await waitFor(() => expect(onDone).toHaveBeenCalled());
    });

    it("reports a name collision as a collision, not a crash", async () => {
        const user = userEvent.setup();
        mocked.update.mockRejectedValue({
            response: { status: 409, data: { detail: "'Vitamin D3' already exists" } },
        } as never);

        renderPage(<SupplementEditor food={OMEGA} onDone={() => {}} />);
        await user.clear(await screen.findByLabelText("Name"));
        await user.type(screen.getByLabelText("Name"), "Vitamin D3");
        await user.click(screen.getByRole("button", { name: "Save" }));

        expect(
            await screen.findByText("'Vitamin D3' already exists"),
        ).toBeInTheDocument();
    });

    it("will not save an empty name", async () => {
        const user = userEvent.setup();
        renderPage(<SupplementEditor food={OMEGA} onDone={() => {}} />);
        await user.clear(await screen.findByLabelText("Name"));

        expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    });
});
