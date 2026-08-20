/**
 * The scale drain control — plan 0015.
 *
 * What is worth mounting is the gating, because both gates fail *silently* in
 * ways a type cannot catch. A browser without Web Bluetooth must not be shown
 * a button that throws when tapped, and a scale whose consent code has never
 * been entered returns an empty replay that looks exactly like an empty ring.
 *
 * The drain itself is not mounted: it needs a GATT server, and the decoding it
 * feeds is covered by `src/lib/bcs.test.ts` against fixture bytes.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import BodyComposition from "./BodyComposition";
import { bodyCompositionApi } from "@/lib/api";
import * as scale from "@/lib/scale";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        bodyCompositionApi: {
            getAll: vi.fn(),
            getStats: vi.fn(),
            getTrends: vi.fn(),
            syncBodySpec: vi.fn(),
            syncScale: vi.fn(),
            delete: vi.fn(),
        },
    };
});

const api = vi.mocked(bodyCompositionApi);

const STATS = {
    total_measurements: 2,
    latest_weight: 188.4,
    latest_body_fat: 18.5,
    latest_muscle_mass: 38.7,
    latest_source: "openscale",
    weight_change: -1.6,
    body_fat_change: -0.2,
    muscle_mass_change: 0.1,
    primary_source: "openscale",
    first_date: "2026-08-19",
    latest_date: "2026-08-20",
};

beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    api.getStats.mockResolvedValue({ data: STATS } as never);
    api.getTrends.mockResolvedValue({
        data: { dates: [], weights: [], body_fats: [], muscle_masses: [], water_pcts: [], sources: [] },
    } as never);
    api.getAll.mockResolvedValue({ data: [] } as never);
    api.delete.mockResolvedValue({ data: {} } as never);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

const withBluetooth = (present: boolean) =>
    vi.spyOn(scale, "isSupported").mockReturnValue(present);

it("hides the control entirely where Web Bluetooth is absent", async () => {
    // Firefox always, and Brave until it is enabled at brave://flags. Showing
    // a disabled button would invite tapping it; showing nothing is honest.
    withBluetooth(false);
    renderPage(<BodyComposition />, "/body-composition");

    await screen.findByText(/Import DEXA scans/i);
    expect(screen.queryByText(/Read scale/i)).not.toBeInTheDocument();
});

it("asks for the consent code before offering to read", async () => {
    // The BF720 gates measurements behind UDS consent. Without it a drain
    // connects, subscribes, and receives nothing - indistinguishable from a
    // scale with an empty ring, so the UI must not let you reach that state.
    withBluetooth(true);
    renderPage(<BodyComposition />, "/body-composition");

    await screen.findByText(/Read scale/i);
    expect(screen.getByPlaceholderText(/Consent code/i)).toBeInTheDocument();
    expect(
        screen.queryByRole("button", { name: /^Read scale$/i }),
    ).not.toBeInTheDocument();
});

it("offers the drain once a slot and code are saved", async () => {
    withBluetooth(true);
    const user = userEvent.setup();
    renderPage(<BodyComposition />, "/body-composition");

    await screen.findByText(/Read scale/i);
    await user.type(screen.getByPlaceholderText(/Consent code/i), "1234");
    await user.click(screen.getByRole("button", { name: /Save/i }));

    const button = await screen.findByRole("button", { name: /^Read scale$/i });
    expect(button).toBeEnabled();
    expect(screen.getByText(/slot 1/i)).toBeInTheDocument();
});

it("remembers the credentials across a remount", async () => {
    withBluetooth(true);
    localStorage.setItem(
        "helf.scale.credentials",
        JSON.stringify({ userIndex: 3, consentCode: 4321 }),
    );
    renderPage(<BodyComposition />, "/body-composition");

    await screen.findByRole("button", { name: /^Read scale$/i });
    expect(screen.getByText(/slot 3/i)).toBeInTheDocument();
});

it("reports a drain that was entirely replay as already held", async () => {
    // The normal outcome, not the edge case: the scale replays all thirty
    // stored weighings every time, so most drains import nothing.
    withBluetooth(true);
    vi.spyOn(scale, "drainScale").mockResolvedValue([
        { timestamp: "2026-08-20T07:31:12", date: "2026-08-20", weight: 188.4 },
    ]);
    api.syncScale.mockResolvedValue({
        data: { readings_received: 1, imported: 0, skipped: 1 },
    } as never);
    localStorage.setItem(
        "helf.scale.credentials",
        JSON.stringify({ userIndex: 1, consentCode: 1234 }),
    );

    const user = userEvent.setup();
    renderPage(<BodyComposition />, "/body-composition");

    await user.click(await screen.findByRole("button", { name: /^Read scale$/i }));

    await waitFor(() =>
        expect(screen.getByText(/1 reading - 0 new, 1 already held/)).toBeInTheDocument(),
    );
});

it("says so plainly when the scale had nothing stored", async () => {
    withBluetooth(true);
    vi.spyOn(scale, "drainScale").mockResolvedValue([]);
    localStorage.setItem(
        "helf.scale.credentials",
        JSON.stringify({ userIndex: 1, consentCode: 1234 }),
    );

    const user = userEvent.setup();
    renderPage(<BodyComposition />, "/body-composition");

    await user.click(await screen.findByRole("button", { name: /^Read scale$/i }));

    await waitFor(() =>
        expect(screen.getByText(/nothing stored/i)).toBeInTheDocument(),
    );
    // An empty ring is not a sync, so nothing should have been posted.
    expect(api.syncScale).not.toHaveBeenCalled();
});

it("surfaces a rejected consent code rather than failing silently", async () => {
    withBluetooth(true);
    vi.spyOn(scale, "drainScale").mockRejectedValue(
        new scale.ScaleError("The scale refused the consent code for slot 1."),
    );
    localStorage.setItem(
        "helf.scale.credentials",
        JSON.stringify({ userIndex: 1, consentCode: 9999 }),
    );

    const user = userEvent.setup();
    renderPage(<BodyComposition />, "/body-composition");

    await user.click(await screen.findByRole("button", { name: /^Read scale$/i }));

    await waitFor(() =>
        expect(screen.getByText(/refused the consent code/i)).toBeInTheDocument(),
    );
});

const measurement = (
    doc_id: number,
    timestamp: string,
    created_at: string,
    weight: number,
) => ({
    doc_id,
    timestamp,
    created_at,
    date: timestamp.slice(0, 10),
    source: "openscale",
    weight,
    weight_unit: "lbs",
    body_fat_pct: null,
    muscle_mass: null,
    water_pct: null,
    bone_mass_kg: null,
    bmi: 31,
    visceral_fat: null,
    metabolic_age: null,
    protein_pct: null,
});

it("asks for the log in ingestion order, not observed order", async () => {
    // The whole reason the table exists: a reset scale files a reading years
    // out of place, and observed order buries it mid-history.
    withBluetooth(false);
    api.getAll.mockResolvedValue({
        data: [measurement(155, "2025-01-01T12:00:36", "2026-08-20T11:33:44", 197.89)],
    } as never);
    renderPage(<BodyComposition />, "/body-composition");

    await screen.findByText(/All measurements/i);
    expect(api.getAll).toHaveBeenCalledWith(
        expect.objectContaining({ sort: "ingested" }),
    );
});

it("shows both timestamps so a bad clock is visible", async () => {
    withBluetooth(false);
    api.getAll.mockResolvedValue({
        data: [measurement(155, "2025-01-01T12:00:36", "2026-08-20T11:33:44", 197.89)],
    } as never);
    renderPage(<BodyComposition />, "/body-composition");

    await screen.findByText("2025-01-01 12:00");
    expect(screen.getByText("2026-08-20 11:33")).toBeInTheDocument();
    expect(screen.getByText("197.9")).toBeInTheDocument();
});

it("takes two taps to delete, and never a browser dialog", async () => {
    // A native confirm() blocks the whole page and cannot be dismissed by
    // anything driving the browser. Two taps is also harder to do by accident.
    withBluetooth(false);
    api.getAll.mockResolvedValue({
        data: [measurement(156, "2026-08-20T11:34:37", "2026-08-20T11:36:08", 198.06)],
    } as never);
    const user = userEvent.setup();
    renderPage(<BodyComposition />, "/body-composition");

    await user.click(await screen.findByRole("button", { name: /Delete/i }));
    expect(api.delete).not.toHaveBeenCalled();

    expect(screen.getByRole("button", { name: /Cancel/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Delete$/i }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith(156));
});

it("cancelling leaves the row alone", async () => {
    withBluetooth(false);
    api.getAll.mockResolvedValue({
        data: [measurement(156, "2026-08-20T11:34:37", "2026-08-20T11:36:08", 198.06)],
    } as never);
    const user = userEvent.setup();
    renderPage(<BodyComposition />, "/body-composition");

    await user.click(await screen.findByRole("button", { name: /Delete/i }));
    await user.click(screen.getByRole("button", { name: /Cancel/i }));

    expect(api.delete).not.toHaveBeenCalled();
    expect(screen.getByText("198.1")).toBeInTheDocument();
});

it("renders nothing at all when there are no measurements", async () => {
    withBluetooth(false);
    api.getAll.mockResolvedValue({ data: [] } as never);
    renderPage(<BodyComposition />, "/body-composition");

    await screen.findByText(/Import DEXA scans/i);
    expect(screen.queryByText(/All measurements/i)).not.toBeInTheDocument();
});

it("carries the measurement count on the table rather than in a tile", async () => {
    // It was a quarter of the stats grid for a number you read once. The tile
    // it vacated went to the drain button; the count went to the one thing it
    // is actually about.
    withBluetooth(false);
    api.getAll.mockResolvedValue({
        data: [measurement(156, "2026-08-20T11:34:37", "2026-08-20T11:36:08", 198.06)],
    } as never);
    renderPage(<BodyComposition />, "/body-composition");

    await screen.findByText(/All measurements/i);
    expect(screen.getByText(/2 total/)).toBeInTheDocument();
    expect(screen.queryByText(/Total Measurements/i)).not.toBeInTheDocument();
});

it("keeps the pairing form reachable with an empty database", async () => {
    // The empty state tells you to read the scale; it used to say that from
    // inside the branch that renders neither control.
    withBluetooth(true);
    api.getStats.mockResolvedValue({ data: null } as never);
    renderPage(<BodyComposition />, "/body-composition");

    await screen.findByText(/NO DATA YET/i);
    expect(screen.getByPlaceholderText(/Consent code/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/BodySpec access token/i)).toBeInTheDocument();
});
