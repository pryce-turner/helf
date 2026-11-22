/**
 * The upcoming queue is one list now (9c4e7b21f806): a generated program and
 * the agent's mobility prescriptions render together, and the mobility
 * element of a workout is a badge on the sets it flags — not a page of its
 * own. The things worth mounting are the merge itself, the per-author
 * renderings (folded routine vs. rows), the transfer naming its session, and
 * the generate warning naming what it wipes.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import Upcoming from "./Upcoming";
import { mobilityApi, upcomingApi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        upcomingApi: {
            ...actual.upcomingApi,
            getAll: vi.fn(),
            transferSession: vi.fn(),
            deleteSession: vi.fn(),
            getPresets: vi.fn(),
            getPreset: vi.fn(),
            generateLiftoscript: vi.fn(),
        },
        mobilityApi: {
            getLastSession: vi.fn(),
        },
    };
});

const upcoming = vi.mocked(upcomingApi);
const mobility = vi.mocked(mobilityApi);

const row = (
    exercise: string,
    reps: number,
    weight: number | null,
    doc_id: number,
    session = 1,
    is_mobility = false,
    comment: string | null = null,
) => ({
    doc_id,
    session,
    is_mobility,
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

const GENERATED_SESSION = {
    session: 7,
    label: null,
    rationale: null,
    generated_at: null,
    items: [
        row("Bench Press", 5, 135, 11, 7),
        row("Bench Press", 5, 135, 12, 7),
    ],
};

const AGENT_SESSION = {
    session: 13,
    label: "Low back",
    rationale: "QL holds at 30lb; pigeon leads while you are fresh.",
    generated_at: "2026-08-10T09:00:00",
    items: [
        row("QL Raise", 8, 30, 21, 13, true),
        row("QL Raise", 8, 30, 22, 13, true),
        row("Weighted Pigeon Squat", 5, 30, 23, 13, true),
    ],
};

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
    ],
};

beforeEach(() => {
    vi.clearAllMocks();
    mobility.getLastSession.mockResolvedValue({ data: null } as never);
    upcoming.getPresets.mockResolvedValue({ data: [] } as never);
    upcoming.getPreset.mockResolvedValue({ data: null } as never);
    // One test mocks the clock to pin down the timezone bug. Reset here rather
    // than at the end of that test, so a failure part-way through cannot leave
    // every later test running in August 2026.
    vi.useRealTimers();
});

it("lists both authors' sessions in one queue, each rendered its own way", async () => {
    upcoming.getAll.mockResolvedValue({
        data: [GENERATED_SESSION, AGENT_SESSION],
    } as never);

    renderPage(<Upcoming />);

    // The generated session: numbered, and every row visible.
    expect(await screen.findByText("Session 7")).toBeInTheDocument();
    expect(screen.getAllByText("Bench Press")).toHaveLength(2);

    // The agent's: labelled, reasoned, and folded back into a prescription.
    expect(screen.getByText("Low back")).toBeInTheDocument();
    expect(
        screen.getByText("QL holds at 30lb; pigeon leads while you are fresh."),
    ).toBeInTheDocument();
    expect(screen.getByText("2 x 8 @ 30lb")).toBeInTheDocument();
    expect(screen.getByText("1 x 5 @ 30lb")).toBeInTheDocument();
    expect(screen.getByText(/2 movements/)).toBeInTheDocument();
});

it("marks the mobility element with a badge on the flagged sets", async () => {
    upcoming.getAll.mockResolvedValue({
        data: [
            {
                session: 3,
                label: null,
                rationale: null,
                generated_at: null,
                items: [
                    row("Romanian Deadlift", 8, 135, 31, 3),
                    row("Pigeon Squat", 5, null, 32, 3, true),
                ],
            },
        ],
    } as never);

    renderPage(<Upcoming />);

    // One flagged row among the lifting sets: one badge, not two.
    expect((await screen.findAllByText("mobility")).length).toBe(1);
});

it("transfers a session using a local date, never a UTC one", async () => {
    upcoming.getAll.mockResolvedValue({ data: [AGENT_SESSION] } as never);
    upcoming.transferSession.mockResolvedValue({
        data: { session: 13, date: "2026-08-11", count: 3, label: "Low back", message: "ok" },
    } as never);

    // Late evening local time. `toISOString()` here spells tomorrow's date
    // west of Greenwich, and `workouts.date` is a string prefix — so the
    // session would land on a day the user never trained.
    vi.setSystemTime(new Date(2026, 7, 11, 22, 30));

    renderPage(<Upcoming />);
    await userEvent.click(await screen.findByText("Transfer"));
    await userEvent.click(screen.getByText(/Transfer to Aug 11, 2026/));

    await waitFor(() =>
        expect(upcoming.transferSession).toHaveBeenCalledWith(13, "2026-08-11"),
    );
});

it("deletes a session only after the confirm is armed", async () => {
    upcoming.getAll.mockResolvedValue({ data: [AGENT_SESSION] } as never);
    upcoming.deleteSession.mockResolvedValue({ data: undefined } as never);

    renderPage(<Upcoming />);
    await userEvent.click(await screen.findByText("Delete"));
    await userEvent.click(screen.getByText("Confirm"));

    await waitFor(() =>
        expect(upcoming.deleteSession).toHaveBeenCalledWith(13),
    );
});

it("shows the last mobility session's comments below the queue", async () => {
    upcoming.getAll.mockResolvedValue({ data: [AGENT_SESSION] } as never);
    mobility.getLastSession.mockResolvedValue({ data: LAST_SESSION } as never);

    renderPage(<Upcoming />);

    expect(await screen.findByText("Last mobility session")).toBeInTheDocument();
    // The feedback is what the next session gets written from.
    expect(
        screen.getByText("failed on right at 7, hit 8 on left"),
    ).toBeInTheDocument();
});

it("shows the last session beside the empty state when the queue is empty", async () => {
    upcoming.getAll.mockResolvedValue({ data: [] } as never);
    mobility.getLastSession.mockResolvedValue({ data: LAST_SESSION } as never);

    renderPage(<Upcoming />);

    expect(await screen.findByText("No upcoming workouts")).toBeInTheDocument();
    expect(screen.getByText(/ask the agent to write a mobility session/)).toBeInTheDocument();
    expect(screen.getByText("Last mobility session")).toBeInTheDocument();
});

it("warns before generating, naming the agent-written sessions it wipes", async () => {
    upcoming.getAll.mockResolvedValue({
        data: [GENERATED_SESSION, AGENT_SESSION],
    } as never);
    upcoming.generateLiftoscript.mockResolvedValue({
        data: { success: true, message: "ok", count: 3, sessions: 1, deleted_count: 5 },
    } as never);

    renderPage(<Upcoming />);

    await userEvent.click(await screen.findByText("Edit program"));
    await userEvent.type(
        screen.getByRole("textbox"),
        "## Day 1\nBench Press / 3x5 135lb",
    );
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    // The warning, not a silent wipe: the agent's session goes with the rest.
    expect(await screen.findByText(/Including the agent-written session/)).toBeInTheDocument();
    expect(screen.getByText(/'Low back'/)).toBeInTheDocument();

    await userEvent.click(screen.getByText("Generate and overwrite"));
    await waitFor(() =>
        expect(upcoming.generateLiftoscript).toHaveBeenCalledWith({
            script: "## Day 1\nBench Press / 3x5 135lb",
            num_cycles: 4,
        }),
    );
});
