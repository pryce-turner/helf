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
import IntervalTimer from "./IntervalTimer";

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
const renderTimer = (saved?: Record<string, number>) => {
    if (saved) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
    return renderPage(<IntervalTimer />, "/timer");
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

const click = (name: string | RegExp) =>
    fireEvent.click(screen.getByRole("button", { name }));

beforeEach(() => {
    beeps.length = 0;
    window.localStorage.clear();
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

it("starts a work phase on Start and counts it down", () => {
    renderTimer();

    click("Start");

    expect(screen.getByText("WORK")).toBeInTheDocument();
    expect(clock()).toHaveTextContent("00:20");
    expect(screen.getByText(/Exercise 1 \/ 5 · Round 1 \/ 2/)).toBeInTheDocument();
    // GO sounds inside the Start tap.
    expect(count(CUE.go)).toBe(1);
    // Settings are locked while the session runs.
    expect(screen.getByRole("button", { name: /^Work/ })).toBeDisabled();

    tick(1100);
    expect(clock()).toHaveTextContent("00:19");
    tick(1000);
    expect(clock()).toHaveTextContent("00:18");
});

it("runs rest between exercises and the reset between rounds, each with its own cue", () => {
    renderTimer(SHORT_CIRCUIT);
    click("Start");

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
    // A 3s rest has room for two high pips (at 2s and 1s), then GO.
    expect(count(CUE.pipBeforeWork)).toBe(2);
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
    click("Start");

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
    click("Start");

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

    click("Start");
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
    click("Start");
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
    expect(clock()).toHaveTextContent("00:05");
});
