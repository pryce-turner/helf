/**
 * The timer's countdown runs on requestAnimationFrame against
 * performance.now() deadlines, and vitest's default fake timers touch
 * neither — so the suite fakes both explicitly and steps the clock by hand.
 * jsdom has no AudioContext and the Start tap constructs one, so that is
 * stubbed too, recording every frequency it is asked to play.
 *
 * Clicks go through fireEvent, not the repo's usual user-event: under fake
 * timers user-event's async internals wait on the very clock the test owns,
 * and the click never returns (verified against a bare button, default fakes
 * included). fireEvent is synchronous, so the only clock movement here is the
 * deliberate kind in tick().
 *
 * Worth mounting because the deadline math is the feature: pause banks the
 * remainder and resume re-anchors it, and a phase boundary carries its
 * overshoot into the next phase. None of that has a type to catch it.
 */
import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import { exercisesApi } from "@/lib/api";
import IntervalTimer from "./IntervalTimer";

/**
 * The pool and the log are the only two things the timer reads or writes, so
 * they are stubbed and everything else — the API client's real interceptors
 * included — comes through untouched.
 */
vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return {
        ...actual,
        exercisesApi: { ...actual.exercisesApi, getMovementBreaks: vi.fn() },
    };
});

const mockedPool = vi.mocked(exercisesApi.getMovementBreaks);

const movement = (overrides: Record<string, unknown> = {}) => ({
    doc_id: 1,
    name: "Deep Squat Hold",
    category: "Legs",
    form: "Sink all the way down and stay there.",
    application: null,
    rating: null,
    default_work_seconds: 40,
    last_used: null,
    use_count: 0,
    created_at: "2026-11-12",
    ...overrides,
});

/** A pool of three, so "not the same one again" is a real assertion. */
const POOL = [
    movement(),
    movement({ doc_id: 2, name: "Wall Angel", category: "Shoulders", default_work_seconds: 40 }),
    movement({ doc_id: 3, name: "Chin Tuck", category: "Back", default_work_seconds: 30 }),
];

/** Every frequency the page asked an oscillator to play, in order. */
const beeps: number[] = [];

/**
 * One frequency that belongs to each cue and to no other, so a test can ask
 * "did the rest cue sound" rather than match a whole chord.
 */
const CUE = {
    go: 1319,
    restFall: 587,
    pipBeforeWork: 988,
    pipBeforeRest: 698,
    bell: 2093,
    roundTap: 440,
    done: 1760,
};

const count = (frequency: number) => beeps.filter((f) => f === frequency).length;

class FakeAudioContext {
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
    createOscillator = vi.fn(() => {
        const osc = {
            type: "",
            frequency: { value: 0 },
            // The page chains `osc.connect(gain).connect(destination)`.
            connect: vi.fn((node: unknown) => node),
            start: vi.fn(),
            stop: vi.fn(),
        };
        osc.start.mockImplementation(() => {
            beeps.push(osc.frequency.value);
        });
        return osc;
    });
}

const STORAGE_KEY = "helf-interval-timer-settings";

/** Mount the page, optionally with settings already saved on the device. */
/**
 * `path` has to stay "/timer" while `route` carries the query: registering the
 * page under a URL with a query string matches no location at all, and the
 * router renders nothing.
 */
const renderTimer = (
    saved?: Record<string, number>,
    route = "/timer",
    path = "/timer",
) => {
    if (saved) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
    return renderPage(<IntervalTimer />, route, path);
};

/** Two 5s exercises, 3s apart, twice, with a 7s reset between the rounds. */
const SHORT_CIRCUIT = {
    workSeconds: 5,
    restSeconds: 3,
    exercises: 2,
    rounds: 2,
    roundRestSeconds: 7,
};

/** Advance the clock; the rAF ticks inside it set state, so act() wraps it. */
const tick = (ms: number) => {
    act(() => {
        vi.advanceTimersByTime(ms);
    });
};

const clock = () => screen.getByRole("timer");

/**
 * Start, and run out the 5s lead-in so the first work is on screen. The
 * extra 20ms is one fake frame past the boundary; the overshoot is carried,
 * so the work's deadline is still exactly 5s after the tap.
 */
const start = () => {
    click("Start");
    tick(5020);
};

const click = (name: string | RegExp) =>
    fireEvent.click(screen.getByRole("button", { name }));

beforeEach(() => {
    beeps.length = 0;
    window.localStorage.clear();
    vi.clearAllMocks();
    mockedPool.mockResolvedValue({ data: [] } as never);
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
    vi.stubGlobal("AudioContext", FakeAudioContext);
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

it("shows the whole session's length and the five rows on first paint", () => {
    renderTimer();

    expect(screen.getByText("READY")).toBeInTheDocument();
    // The defaults are the screenshot's: 5 × 20s work with 4 × 10s rest
    // between, twice, plus one 10s reset = 290s.
    expect(clock()).toHaveTextContent("04:50");
    expect(screen.getByText("5 exercises × 2 rounds")).toBeInTheDocument();

    for (const name of [
        /^Work 00:20$/,
        /^Rest 00:10$/,
        /^Exercises 5$/,
        /^Rounds 2X$/,
        /^Round Reset 00:10$/,
    ]) {
        expect(screen.getByRole("button", { name })).toBeEnabled();
    }

    expect(screen.getByRole("button", { name: "Start" })).toBeEnabled();
    // Nothing to reset before anything has run.
    expect(screen.queryByRole("button", { name: "Reset" })).toBeNull();
});

it("opens a row's stepper on tap and applies it to the session length", () => {
    renderTimer();

    expect(screen.queryByLabelText("Exercises")).toBeNull();
    click(/^Exercises/);
    expect(screen.getByLabelText("Exercises")).toHaveValue(5);

    click("Decrease Exercises");

    expect(screen.getByRole("button", { name: /^Exercises 4$/ })).toBeInTheDocument();
    // 4 × 20 + 3 × 10, twice, + 10 = 230s.
    expect(clock()).toHaveTextContent("03:50");

    // Turning the reset off puts the ordinary rest between rounds instead.
    click(/^Round Reset/);
    click("Decrease Round Reset");
    click("Decrease Round Reset");
    expect(screen.getByRole("button", { name: /^Round Reset Off$/ })).toBeInTheDocument();
    expect(clock()).toHaveTextContent("03:50");
});

it("loads settings saved before the exercises row existed as one per round", () => {
    renderTimer({ workSeconds: 20, restSeconds: 10, rounds: 8, roundRestSeconds: 0 });

    // The old schedule unchanged: 8 × 20s with 7 × 10s rest = 230s.
    expect(screen.getByRole("button", { name: /^Exercises 1$/ })).toBeInTheDocument();
    expect(clock()).toHaveTextContent("03:50");
});

it("counts down 5s to GO before the first work, and only then", () => {
    renderTimer();

    click("Start");

    expect(screen.getByText("GET READY")).toBeInTheDocument();
    expect(clock()).toHaveTextContent("00:05");
    // Settings are locked from the tap, lead-in included.
    expect(screen.getByRole("button", { name: /^Work/ })).toBeDisabled();
    // Silent until the last three seconds, then high pips towards GO.
    expect(count(CUE.go)).toBe(0);
    tick(1100);
    expect(count(CUE.pipBeforeWork)).toBe(0);
    tick(3920);

    expect(screen.getByText("WORK")).toBeInTheDocument();
    expect(clock()).toHaveTextContent("00:20");
    expect(screen.getByText(/Exercise 1 \/ 5 · Round 1 \/ 2/)).toBeInTheDocument();
    expect(count(CUE.pipBeforeWork)).toBe(3);
    expect(count(CUE.go)).toBe(1);

    tick(1100);
    expect(clock()).toHaveTextContent("00:19");
    tick(1000);
    expect(clock()).toHaveTextContent("00:18");
});

it("runs rest between exercises and the reset between rounds, each with its own cue", () => {
    renderTimer(SHORT_CIRCUIT);
    start();

    tick(5100);
    expect(screen.getByText("REST")).toBeInTheDocument();
    // The rest keeps its work's exercise and round.
    expect(
        screen.getByRole("timer", { name: /REST, exercise 1 of 2, round 1 of 2/ }),
    ).toHaveTextContent("00:03");
    // Three low pips as the work ran out, then the falling rest cue.
    expect(count(CUE.pipBeforeRest)).toBe(3);
    expect(count(CUE.restFall)).toBe(1);

    tick(3000);
    expect(
        screen.getByRole("timer", { name: /WORK, exercise 2 of 2, round 1 of 2/ }),
    ).toHaveTextContent("00:05");
    // A 3s rest has room for two high pips (at 2s and 1s), then GO — on top
    // of the lead-in's three.
    expect(count(CUE.pipBeforeWork)).toBe(5);
    expect(count(CUE.go)).toBe(2);

    // The last exercise of a round ends on the bell, and one tap for round 1
    // — not the rest cue.
    tick(5000);
    expect(
        screen.getByRole("timer", { name: /ROUND RESET, exercise 2 of 2, round 1 of 2/ }),
    ).toHaveTextContent("00:07");
    expect(count(CUE.bell)).toBe(2);
    expect(count(CUE.roundTap)).toBe(1);
    expect(count(CUE.restFall)).toBe(1);

    tick(7000);
    expect(
        screen.getByRole("timer", { name: /WORK, exercise 1 of 2, round 2 of 2/ }),
    ).toBeInTheDocument();
    expect(count(CUE.go)).toBe(3);
});

it("rings the round bell, not the rest cue, when the reset is off", () => {
    renderTimer({ ...SHORT_CIRCUIT, exercises: 1, rounds: 3, roundRestSeconds: 0 });
    start();

    // Round 1's only exercise ends into the ordinary rest.
    tick(5100);
    expect(screen.getByText("REST")).toBeInTheDocument();
    expect(count(CUE.bell)).toBe(2);
    expect(count(CUE.restFall)).toBe(0);
    expect(count(CUE.roundTap)).toBe(1);

    // Round 2 ends: two taps this time, three in all. One tick per phase —
    // the loop re-arms on each phase change, which needs a render between.
    tick(3000);
    tick(5000);
    expect(count(CUE.roundTap)).toBe(3);
});

it("follows the round bell with GO when nothing separates the rounds", () => {
    renderTimer({ ...SHORT_CIRCUIT, exercises: 1, restSeconds: 0, roundRestSeconds: 0 });
    start();

    tick(5100);
    expect(
        screen.getByRole("timer", { name: /WORK, exercise 1 of 1, round 2 of 2/ }),
    ).toBeInTheDocument();
    // Both cues are scheduled at the one boundary: bell for the round, GO for
    // the work that starts straight after it.
    expect(count(CUE.bell)).toBe(2);
    expect(count(CUE.go)).toBe(2);
});

it("freezes the countdown on Pause and picks it back up on Resume", () => {
    renderTimer();

    start();
    tick(1100);
    expect(clock()).toHaveTextContent("00:19");

    click("Pause");
    expect(screen.getByText(/Paused/)).toBeInTheDocument();

    // Five seconds pass and the banked remainder does not move.
    tick(5000);
    expect(clock()).toHaveTextContent("00:19");

    click("Resume");
    tick(1100);
    expect(clock()).toHaveTextContent("00:18");
});

it("shows DONE with the closing run once every round has run", () => {
    // One 5s exercise, one round: the shortest session the settings allow.
    renderTimer({ ...SHORT_CIRCUIT, exercises: 1, rounds: 1 });
    start();
    expect(screen.getByText(/Exercise 1 \/ 1 · Round 1 \/ 1/)).toBeInTheDocument();

    tick(5100);

    expect(screen.getByText("DONE")).toBeInTheDocument();
    expect(screen.getByText("1 round complete")).toBeInTheDocument();
    expect(clock()).toHaveTextContent("00:00");
    // The final round's end is the session's: the run, not the bell.
    expect(count(CUE.done)).toBe(1);
    expect(count(CUE.bell)).toBe(0);
    expect(screen.getByRole("button", { name: "Go again" })).toBeEnabled();

    click("Reset");
    expect(screen.getByText("READY")).toBeInTheDocument();
    // The workout's own length: the lead-in is not part of it.
    expect(clock()).toHaveTextContent("00:05");

    // Go again gets the lead-in too — once per session, not once per page.
    click("Start");
    expect(screen.getByText("GET READY")).toBeInTheDocument();
});

// --- Movement break -----------------------------------------------------------------

/**
 * Let the pool query land.
 *
 * Not `waitFor`: it waits on a timer, and this suite fakes timers — so it
 * would sit there until the test's own timeout. The query resolves on
 * microtasks, which an async act() drains.
 */
const settle = async () => {
    // Not `waitFor`, which waits on a timer — and this suite fakes timers, so
    // it would sit until the test's own timeout. And not one big act(): React
    // Query resolves over several turns with a commit between them, and under
    // fake timers the commit needs a clock tick to run, hence the 0ms advance.
    for (let i = 0; i < 4; i++) {
        await act(async () => {
            vi.advanceTimersByTime(0);
            await Promise.resolve();
        });
    }
};

const poolOf = (pool = POOL) => {
    mockedPool.mockResolvedValue({ data: pool } as never);
    return pool;
};

/** Shuffle, and assume the pool has arrived. */
const shuffle = (label = /Movement break/) =>
    fireEvent.click(screen.getByRole("button", { name: label }));

/** Five seconds of work, so a run finishes inside a test. */
const setWorkTo = (seconds: number) => {
    fireEvent.click(screen.getByRole("button", { name: /^Work/ }));
    fireEvent.change(screen.getByLabelText("Work"), {
        target: { value: String(seconds) },
    });
};

it("offers no shuffle when the pool is empty", async () => {
    renderTimer();
    await settle();

    expect(mockedPool).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Movement break/ })).toBeNull();
});

it("sets the times from the movement it shuffles", async () => {
    poolOf();
    renderTimer();
    await settle();

    shuffle();

    expect(screen.getByText("Deep Squat Hold")).toBeInTheDocument();
    // The movement's own bout, and a rest at half of it.
    expect(screen.getByRole("button", { name: /^Work 00:40$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Rest 00:20$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Exercises 2$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Rounds 1X$/ })).toBeInTheDocument();
    // 40 + 20 + 40 = 100s, with nothing after the last work.
    expect(clock()).toHaveTextContent("01:40");
    // The cue is on the page while the interval runs, not behind a tap.
    expect(screen.getByText(/Sink all the way down/)).toBeInTheDocument();
});

it("keeps the movement when a time is adjusted afterwards", async () => {
    poolOf();
    renderTimer();
    await settle();
    shuffle();

    setWorkTo(35);

    // The shuffle picked the movement; the rows only ever pick the times.
    expect(screen.getByRole("button", { name: /^Work 00:35$/ })).toBeInTheDocument();
    expect(screen.getByText("Deep Squat Hold")).toBeInTheDocument();
});

it("opens straight onto a movement when entered from the mobility tab", async () => {
    poolOf();
    renderTimer(undefined, "/timer?break=1");
    await settle();

    expect(screen.getAllByText(/Deep Squat Hold|Wall Angel|Chin Tuck/)).toHaveLength(1);
    // And it did not leave the button behind.
    expect(screen.queryByRole("button", { name: /Movement break —/ })).toBeNull();
});

it("never shuffles the movement it is already showing", async () => {
    poolOf([movement(), movement({ doc_id: 2, name: "Wall Angel" })]);
    renderTimer(undefined, "/timer?break=1");
    await settle();

    const first = screen.getByText(/Deep Squat Hold|Wall Angel/).textContent;
    // With two in the pool, the only candidate left is the other one.
    shuffle(/Shuffle a different movement/);
    expect(screen.getByText(/Deep Squat Hold|Wall Angel/).textContent).not.toBe(first);
});
