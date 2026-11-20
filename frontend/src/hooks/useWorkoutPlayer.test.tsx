/**
 * The day player hook, mounted headless with the same fake-timer discipline
 * the interval timer's suite established: rAF and performance.now() are
 * faked explicitly, the clock moves by hand, and the only API the hook talks
 * to is stubbed. Worth mounting because the writes it makes — once per tile,
 * from the immutable snapshot, excluding paused time — are the feature.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { workoutsApi } from "@/lib/api";
import { useWorkoutPlayer } from "./useWorkoutPlayer";
import type { PlayerTile } from "@/lib/workoutPlayer";

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        workoutsApi: {
            ...actual.workoutsApi,
            perform: vi.fn(),
            recordRestAfter: vi.fn(),
        },
    };
});

const perform = vi.mocked(workoutsApi.perform);
const recordRestAfter = vi.mocked(workoutsApi.recordRestAfter);

const tile = (overrides: Partial<PlayerTile> = {}): PlayerTile => ({
    doc_id: 1,
    exercise: "Farmer Carry",
    reps: 2,
    work_seconds: 40,
    rest_seconds: 20,
    rest_after_seconds: 15,
    ...overrides,
});

const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider
        client={
            new QueryClient({
                defaultOptions: {
                    queries: { retry: false, gcTime: 0 },
                    mutations: { retry: false },
                },
            })
        }
    >
        {children}
    </QueryClientProvider>
);

const mount = (initialIncomplete: PlayerTile[] = []) =>
    renderHook((props: PlayerTile[]) => useWorkoutPlayer(props), {
        wrapper,
        initialProps: initialIncomplete,
    });

type HookResult = ReturnType<typeof mount>["result"];

/** Advance the clock; the rAF ticks inside it set state, so act() wraps it. */
const tick = (ms: number) => {
    act(() => {
        vi.advanceTimersByTime(ms);
    });
};

/** Drain the promise a save resolves on, through the fake clock. */
const settle = async () => {
    for (let i = 0; i < 4; i++) {
        await act(async () => {
            vi.advanceTimersByTime(0);
            await Promise.resolve();
        });
    }
};

/** Play and run out the 5s get-ready, with one fake frame of overshoot. */
const play = (result: HookResult, tiles: PlayerTile[]) => {
    act(() => result.current.play(tiles));
    tick(5020);
};

beforeEach(() => {
    vi.clearAllMocks();
    perform.mockResolvedValue({ data: {} } as never);
    recordRestAfter.mockResolvedValue({ data: {} } as never);
    vi.useFakeTimers({
        toFake: [
            "setTimeout",
            "clearTimeout",
            "setInterval",
            "clearInterval",
            "Date",
            "performance",
            "requestAnimationFrame",
            "cancelAnimationFrame",
        ],
    });
    vi.stubGlobal(
        "AudioContext",
        class {
            state = "running";
            currentTime = 0;
            destination = {};
            resume = vi.fn(() => Promise.resolve());
            close = vi.fn(() => Promise.resolve());
            createGain = vi.fn(() => ({
                gain: {
                    setValueAtTime: vi.fn(),
                    exponentialRampToValueAtTime: vi.fn(),
                },
                connect: vi.fn(),
            }));
            createOscillator = vi.fn(() => ({
                type: "",
                frequency: { value: 0 },
                connect: vi.fn((node: unknown) => node),
                start: vi.fn(),
                stop: vi.fn(),
            }));
        },
    );
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

it("plays the get-ready once, then work and rest per rep, and writes the tile once", async () => {
    const { result } = mount();
    play(result, [tile()]);

    expect(result.current.phase?.kind).toBe("work");
    expect(result.current.progressLabel).toBe("Set 1 · rep 1 / 2");
    expect(result.current.status).toBe("running");

    // 40s work, 20s rest, 40s work — then the tile is written before the run
    // can end.
    tick(40_100);
    expect(result.current.phase?.kind).toBe("rest");
    expect(result.current.progressLabel).toBe("Set 1 · rep 1 / 2");
    tick(20_100);
    expect(result.current.phase?.kind).toBe("work");
    expect(result.current.progressLabel).toBe("Set 1 · rep 2 / 2");
    tick(40_100);

    await settle();
    expect(perform).toHaveBeenCalledTimes(1);
    // From the snapshot, in totals: 2 reps of 40s, one 20s rest between.
    expect(perform).toHaveBeenCalledWith(1, {
        ended_early: false,
        completed_reps: 2,
        actual_work_seconds: 80,
        actual_rest_seconds: 20,
    });
    expect(result.current.status).toBe("done");
});

it("skips a zero rest entirely", async () => {
    const { result } = mount();
    play(result, [tile({ rest_seconds: 0, rest_after_seconds: 0 })]);

    tick(40_100);
    expect(result.current.phase?.kind).toBe("work");
    expect(result.current.progressLabel).toBe("Set 1 · rep 2 / 2");
});

it("runs the rest divider between tiles and never after the last", async () => {
    const { result } = mount();
    play(result, [tile(), tile({ doc_id: 2 })]);

    // Through tile 1: work, rest, work.
    tick(40_100);
    tick(20_100);
    tick(40_100);
    await settle();
    expect(result.current.phase?.kind).toBe("restAfter");
    expect(result.current.progressLabel).toBe("Rest after set 1");

    // The divider completes and is recorded on the tile it followed.
    tick(15_100);
    await settle();
    expect(recordRestAfter).toHaveBeenCalledTimes(1);
    expect(recordRestAfter).toHaveBeenCalledWith(1, 15);
    expect(result.current.phase?.kind).toBe("work");
    expect(result.current.progressLabel).toBe("Set 2 · rep 1 / 2");
});

it("freezes on Pause and excludes the paused wall time from the actuals", async () => {
    const { result } = mount();
    play(result, [tile()]);

    tick(10_000);
    act(() => result.current.pause());
    const banked = result.current.remainingMs;

    // Five wall seconds pass paused: nothing counts down.
    tick(5_000);
    expect(result.current.remainingMs).toBe(banked);

    act(() => result.current.resume());
    tick(1_100);
    expect(result.current.remainingMs).toBeLessThan(banked);

    // Stop 2s into the resumed rep: 12s of measured work, not 17.
    tick(900);
    act(() => result.current.stop());
    await settle();
    expect(perform).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
            ended_early: true,
            completed_reps: 0,
            actual_work_seconds: 12,
        }),
    );
});

it("writes measured actuals on a Stop mid-work and leaves later tiles planned", async () => {
    const { result } = mount();
    play(result, [tile(), tile({ doc_id: 2 })]);

    // Finish tile 1, then 12s into tile 2's first rep: Stop.
    tick(40_100);
    tick(20_100);
    tick(40_100);
    await settle();
    tick(15_100); // the divider
    await settle();
    tick(12_000);
    act(() => result.current.stop());
    await settle();

    const tile2Writes = perform.mock.calls.filter((call) => call[0] === 2);
    expect(tile2Writes).toHaveLength(1);
    expect(tile2Writes[0][1]).toMatchObject({
        ended_early: true,
        completed_reps: 0,
        actual_work_seconds: 12,
        actual_rest_seconds: 0,
    });
    // The earlier tile stayed complete; nothing else was written.
    expect(perform).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("done");
});

it("records only the partial rest-after on a Stop during the divider", async () => {
    const { result } = mount();
    play(result, [tile(), tile({ doc_id: 2 })]);

    tick(40_100);
    tick(20_100);
    tick(40_100);
    await settle();
    expect(result.current.phase?.kind).toBe("restAfter");

    // 6s into the 15s divider: Stop. Tile 2 is never performed.
    tick(6_000);
    act(() => result.current.stop());
    await settle();

    expect(recordRestAfter).toHaveBeenCalledWith(1, 6);
    expect(perform).toHaveBeenCalledTimes(1);
});

it("writes nothing on a Stop during get-ready", async () => {
    const { result } = mount();
    act(() => result.current.play([tile()]));

    tick(2_000);
    act(() => result.current.stop());
    await settle();

    expect(perform).not.toHaveBeenCalled();
    expect(recordRestAfter).not.toHaveBeenCalled();
    expect(result.current.status).toBe("idle");
});

it("waits for a manual completion on an untimed tile", async () => {
    const { result } = mount();
    play(result, [tile({ work_seconds: null, rest_seconds: null, reps: 8 })]);

    expect(result.current.phase?.kind).toBe("manual");
    expect(result.current.progressLabel).toBe("Set 1 · press when done");
    // No countdown is invented for it.
    tick(10_000);
    expect(result.current.phase?.kind).toBe("manual");
    expect(perform).not.toHaveBeenCalled();

    act(() => result.current.completeSet());
    await settle();
    expect(perform).toHaveBeenCalledWith(1, {
        ended_early: false,
        completed_reps: 8,
    });
    expect(result.current.status).toBe("done");
});

it("halts on a failed write and retries the same snapshot, exactly once", async () => {
    perform
        .mockRejectedValueOnce(new Error("offline"))
        .mockResolvedValue({ data: {} } as never);
    const { result } = mount();
    play(result, [tile()]);

    tick(40_100);
    tick(20_100);
    tick(40_100);
    await settle();

    expect(result.current.status).toBe("error");
    expect(perform).toHaveBeenCalledTimes(1);

    // The tile is edited between the failure and the retry; the retry must
    // still write the run's snapshot, not the edit.
    act(() => result.current.retry());
    await settle();

    expect(perform).toHaveBeenCalledTimes(2);
    expect(perform).toHaveBeenNthCalledWith(2, 1, {
        ended_early: false,
        completed_reps: 2,
        actual_work_seconds: 80,
        actual_rest_seconds: 20,
    });
    expect(result.current.status).toBe("done");
});

it("re-arms when new incomplete tiles arrive after a run is done", async () => {
    const { result, rerender } = mount([tile()]);
    play(result, [tile()]);

    tick(40_100);
    tick(20_100);
    tick(40_100);
    await settle();
    expect(result.current.status).toBe("done");

    // A movement-break suggestion lands from outside the run. The plan: a
    // later Play starts at the next incomplete tile, so the player must not
    // sit in `done` waiting for a reload.
    rerender([tile({ doc_id: 2 })]);
    expect(result.current.status).toBe("idle");
});

it("does not re-arm from a failed write — the Retry snapshot is preserved", async () => {
    perform
        .mockRejectedValueOnce(new Error("offline"))
        .mockResolvedValue({ data: {} } as never);
    const { result, rerender } = mount([tile()]);
    play(result, [tile()]);

    tick(40_100);
    tick(20_100);
    tick(40_100);
    await settle();
    expect(result.current.status).toBe("error");

    // A suggestion arriving mid-incident must not clear the error state:
    // that is where the failed write's snapshot lives for Retry.
    rerender([tile(), tile({ doc_id: 2 })]);
    expect(result.current.status).toBe("error");

    act(() => result.current.retry());
    await settle();
    expect(perform).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("done");
});

it("cancels a permanently failed write back to idle, with no phantom retry", async () => {
    perform.mockRejectedValue(new Error("offline"));
    const { result } = mount();
    play(result, [tile()]);

    tick(40_100);
    tick(20_100);
    tick(40_100);
    await settle();
    expect(result.current.status).toBe("error");

    act(() => result.current.cancel());

    // The user walks away from the write: back to a plain day, the row
    // editable and deletable again, and nothing written twice later.
    expect(result.current.status).toBe("idle");
    expect(result.current.tiles).toHaveLength(0);
    expect(perform).toHaveBeenCalledTimes(1);
});
