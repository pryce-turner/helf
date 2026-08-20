/**
 * The page has exactly two states and the discriminator comes from the server,
 * so the thing worth mounting is that each state renders what makes it
 * actionable — the routine and a way to date it, or the last session's
 * comments and what to do about them.
 *
 * The set-folding is the other reason. Storage is one row per set and the page
 * reads them back as "2 x 8"; that transform has no type to catch it.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import Mobility from "./Mobility";
import { mobilityApi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        mobilityApi: {
            getPending: vi.fn(),
            transfer: vi.fn(),
            clearPending: vi.fn(),
        },
    };
});

const mobility = vi.mocked(mobilityApi);

const row = (
    exercise: string,
    reps: number,
    weight: number | null,
    comment: string | null,
    doc_id: number,
) => ({
    doc_id,
    session: 1,
    kind: "mobility" as const,
    exercise,
    category: "Core",
    weight,
    weight_unit: "lbs",
    reps,
    distance: null,
    distance_unit: null,
    time: null,
    comment,
    created_at: "2026-08-10T09:00:00",
});

const LAST_SESSION = {
    date: "2026-08-08",
    rationale: "Pigeon restructured around the right-side asymmetry.",
    sets: [
        {
            exercise: "Copenhagen Raise",
            weight: 15,
            reps: 7,
            time: null,
            comment: "failed on right at 7, hit 8 on left",
            order: 1,
            completed: true,
        },
        {
            exercise: "QL Raise",
            weight: 30,
            reps: 10,
            time: null,
            comment: null,
            order: 2,
            completed: true,
        },
    ],
};

beforeEach(() => {
    vi.clearAllMocks();
    // One test mocks the clock to pin down the timezone bug. Reset here rather
    // than at the end of that test, so a failure part-way through cannot leave
    // every later test running in August 2026.
    vi.useRealTimers();
});

it("folds consecutive sets of one movement back into a prescription", async () => {
    mobility.getPending.mockResolvedValue({
        data: {
            ready: true,
            sessions: [
                {
                    session: 1,
                    label: "Low back",
                    generated_at: "2026-08-10T09:00:00",
                    rationale: "QL holds at 30lb; pigeon leads while you are fresh.",
                    items: [
                        row("QL Raise", 8, 30, "each side", 1),
                        row("QL Raise", 8, 30, "each side", 2),
                        row("Weighted Pigeon Squat", 5, 30, "lead with the right", 3),
                    ],
                },
            ],
            last_session: null,
        },
    } as never);

    renderPage(<Mobility />);

    expect(await screen.findByText("2 x 8 @ 30lb")).toBeInTheDocument();
    expect(screen.getByText("1 x 5 @ 30lb")).toBeInTheDocument();
    // Two rows for one movement is one line, so the count is movements.
    expect(screen.getByText(/2 movements/)).toBeInTheDocument();
    expect(
        screen.getByText("QL holds at 30lb; pigeon leads while you are fresh."),
    ).toBeInTheDocument();
});

it("transfers the session using a local date, never a UTC one", async () => {
    mobility.getPending.mockResolvedValue({
        data: {
            ready: true,
            sessions: [
                {
                    session: 4,
                    label: "Shoulder",
                    generated_at: "2026-08-10T09:00:00",
                    rationale: "hold",
                    items: [row("QL Raise", 8, 30, null, 1)],
                },
            ],
            last_session: null,
        },
    } as never);
    mobility.transfer.mockResolvedValue({
        data: { date: "2026-08-11", count: 1, message: "ok" },
    } as never);

    // Late evening local time. `toISOString()` here spells tomorrow's date
    // west of Greenwich, and `workouts.date` is a string prefix — so the
    // session would land on a day the user never trained.
    vi.setSystemTime(new Date(2026, 7, 11, 22, 30));

    renderPage(<Mobility />);
    await userEvent.click(await screen.findByText("Copy to calendar"));
    await userEvent.click(screen.getByText(/Copy to Aug 11, 2026/));

    await waitFor(() =>
        expect(mobility.transfer).toHaveBeenCalledWith("2026-08-11", 4),
    );
});

it("shows what the next session gets written from when nothing is pending", async () => {
    mobility.getPending.mockResolvedValue({
        data: {
            ready: false,
            items: [],
            rationale: null,
            generated_at: null,
            last_session: LAST_SESSION,
        },
    } as never);

    renderPage(<Mobility />);

    expect(await screen.findByText("NO SESSION READY")).toBeInTheDocument();
    expect(screen.getByText(/Ask the agent to generate it/)).toBeInTheDocument();
    // The empty state is only actionable because the feedback is on it.
    expect(
        screen.getByText("failed on right at 7, hit 8 on left"),
    ).toBeInTheDocument();
});

it("says so when the last session was logged with no comments", async () => {
    mobility.getPending.mockResolvedValue({
        data: {
            ready: false,
            items: [],
            rationale: null,
            generated_at: null,
            last_session: {
                ...LAST_SESSION,
                sets: LAST_SESSION.sets.map((s) => ({ ...s, comment: null })),
            },
        },
    } as never);

    renderPage(<Mobility />);

    expect(
        await screen.findByText(/Comments on logged sets are what the next one/),
    ).toBeInTheDocument();
});

it("offers no first session when nothing has ever been logged", async () => {
    mobility.getPending.mockResolvedValue({
        data: {
            ready: false,
            items: [],
            rationale: null,
            generated_at: null,
            last_session: null,
        },
    } as never);

    renderPage(<Mobility />);

    expect(await screen.findByText("NO SESSION READY")).toBeInTheDocument();
    expect(
        screen.getByText(/generate one from the mobility exercise pool/),
    ).toBeInTheDocument();
});

it("lists every pending session, each with its own label and controls", async () => {
    mobility.getPending.mockResolvedValue({
        data: {
            ready: true,
            sessions: [
                {
                    session: 1,
                    label: "Low back",
                    generated_at: "2026-08-19T09:00:00",
                    rationale: "QL first while you are fresh.",
                    items: [row("QL Raise", 8, 30, null, 1)],
                },
                {
                    session: 2,
                    label: "Shoulder",
                    generated_at: "2026-08-20T09:00:00",
                    rationale: "Lock 3 daily, light.",
                    items: [row("Lock 3", 20, 2.5, null, 1)],
                },
            ],
            last_session: null,
        },
    } as never);
    mobility.transfer.mockResolvedValue({
        data: { date: "2026-08-21", count: 1, label: "Shoulder", message: "ok" },
    } as never);
    vi.setSystemTime(new Date(2026, 7, 21, 9, 0));

    renderPage(<Mobility />);

    expect(await screen.findByText("LOW BACK")).toBeInTheDocument();
    expect(screen.getByText("SHOULDER")).toBeInTheDocument();
    expect(screen.getByText("QL first while you are fresh.")).toBeInTheDocument();
    expect(screen.getByText("Lock 3 daily, light.")).toBeInTheDocument();

    // Each card carries its own controls, and transferring names its session —
    // picking one of several is the whole point of the list.
    const copyButtons = screen.getAllByText("Copy to calendar");
    expect(copyButtons).toHaveLength(2);

    await userEvent.click(copyButtons[1]);
    await userEvent.click(screen.getByText(/Copy to Aug 21, 2026/));

    await waitFor(() =>
        expect(mobility.transfer).toHaveBeenCalledWith("2026-08-21", 2),
    );
});
