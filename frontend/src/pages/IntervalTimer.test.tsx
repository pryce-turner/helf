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

const renderTimer = () => renderPage(<IntervalTimer />, "/timer");

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

it("renders the settings rows and an idle countdown on first paint", () => {
    renderTimer();

    expect(screen.getByText("READY")).toBeInTheDocument();
    expect(clock()).toHaveTextContent("00:20");
    expect(screen.getByText("Round 1 / 8")).toBeInTheDocument();

    // The four rows, at their defaults off a clean localStorage.
    expect(screen.getByLabelText("Work")).toHaveValue(20);
    expect(screen.getByLabelText("Rest")).toHaveValue(10);
    expect(screen.getByLabelText("Rounds")).toHaveValue(8);
    expect(screen.getByLabelText("Round rest")).toHaveValue(0);

    expect(screen.getByRole("button", { name: "Start" })).toBeEnabled();
    // Nothing to reset before anything has run.
    expect(screen.getByRole("button", { name: /reset/i })).toBeDisabled();
});

it("starts a work phase on Start and counts it down", () => {
    renderTimer();

    click("Start");

    expect(screen.getByText("WORK")).toBeInTheDocument();
    expect(clock()).toHaveTextContent("00:20");
    // The phase-start chime fires inside the Start tap.
    expect(beeps).toContain(1046);

    tick(1100);
    expect(clock()).toHaveTextContent("00:19");
    tick(1000);
    expect(clock()).toHaveTextContent("00:18");
});

it("moves from work to rest at the deadline and chimes the change", () => {
    renderTimer();

    // 20s default down to the 5s minimum, so the boundary is one step away.
    for (let i = 0; i < 3; i++) click("Decrease Work");
    click("Start");
    expect(clock()).toHaveTextContent("00:05");

    tick(5100);

    expect(screen.getByText("REST")).toBeInTheDocument();
    // The rest keeps its work's round number and runs the full 10s.
    expect(
        screen.getByRole("timer", { name: /REST, round 1 of 8/ }),
    ).toHaveTextContent("00:10");
    // 659Hz is the rest chime; 880Hz alone would be only countdown ticks.
    expect(beeps).toContain(659);
});

it("freezes the countdown on Pause and picks it back up on Resume", () => {
    renderTimer();

    click("Start");
    tick(1100);
    expect(clock()).toHaveTextContent("00:19");

    click(/pause/i);
    expect(screen.getByText(/Paused/)).toBeInTheDocument();

    // Five seconds pass and the banked remainder does not move.
    tick(5000);
    expect(clock()).toHaveTextContent("00:19");

    click(/resume/i);
    tick(1100);
    expect(clock()).toHaveTextContent("00:18");
});

it("shows DONE with the closing chime once every round has run", () => {
    renderTimer();

    // One 5s round: the shortest session the settings allow.
    for (let i = 0; i < 3; i++) click("Decrease Work");
    for (let i = 0; i < 7; i++) click("Decrease Rounds");
    click("Start");
    expect(screen.getByText("Round 1 / 1")).toBeInTheDocument();

    tick(5100);

    expect(screen.getByText("DONE")).toBeInTheDocument();
    expect(screen.getByText("1 round complete")).toBeInTheDocument();
    expect(clock()).toHaveTextContent("00:00");
    // 1108Hz and 1318Hz exist only in the session-done arpeggio.
    expect(beeps).toContain(1108);
    expect(beeps).toContain(1318);
    expect(screen.getByRole("button", { name: /go again/i })).toBeEnabled();
});
