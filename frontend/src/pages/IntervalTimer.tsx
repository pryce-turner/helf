import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Minus,
  Pause,
  Play,
  Plus,
  RotateCcw,
} from "lucide-react";
import Navigation from "@/components/Navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

/**
 * Client-side interval timer — work/rest rounds in the spirit of a
 * minimalist HIIT timer: one big countdown, phase-colored, nothing else.
 *
 * Two things worth knowing about how it works:
 *
 * Timing is anchored to absolute deadlines, never decremented. Each phase
 * stores `endAt = performance.now() + duration` and a rAF loop reads the
 * remainder off that; a busy frame shows up once as a shorter frame, and the
 * overshoot is carried into the next phase's deadline so the session does not
 * drift a frame later every phase. Pause banks the remainder; resume sets a
 * fresh deadline from it.
 *
 * Beeps are driven by the same rAF loop, which means they only fire while the
 * page is in the foreground. Scheduling them ahead on the AudioContext clock
 * would make them sound from a backgrounded tab, at the cost of a second
 * timing system to keep in step with the first — not worth it for a workout
 * timer the user is looking at.
 */

interface TimerSettings {
  workSeconds: number;
  restSeconds: number;
  rounds: number;
  /** 0 = no extra rest between rounds. */
  roundRestSeconds: number;
}

type PhaseKind = "work" | "rest" | "roundRest";

interface Phase {
  kind: PhaseKind;
  /** 1-based round this phase belongs to (rest/roundRest share their work's). */
  round: number;
  durationMs: number;
}

type Status = "idle" | "running" | "paused" | "done";

const STORAGE_KEY = "helf-interval-timer-settings";

const DEFAULT_SETTINGS: TimerSettings = {
  workSeconds: 20,
  restSeconds: 10,
  rounds: 8,
  roundRestSeconds: 0,
};

const clampInt = (
  value: unknown,
  min: number,
  max: number,
  fallback: number,
): number => {
  const n = typeof value === "number" ? value : NaN;
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.round(n)));
};

const loadSettings = (): TimerSettings => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<TimerSettings>;
    return {
      workSeconds: clampInt(parsed.workSeconds, 5, 3600, DEFAULT_SETTINGS.workSeconds),
      restSeconds: clampInt(parsed.restSeconds, 0, 3600, DEFAULT_SETTINGS.restSeconds),
      rounds: clampInt(parsed.rounds, 1, 99, DEFAULT_SETTINGS.rounds),
      roundRestSeconds: clampInt(
        parsed.roundRestSeconds,
        0,
        3600,
        DEFAULT_SETTINGS.roundRestSeconds,
      ),
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
};

/**
 * The schedule as an explicit list: one work phase per round, rests between
 * rounds, and a round rest (when set) after each non-final round's rest.
 * Building it as a list — rather than computing the phase from elapsed time —
 * is what keeps the state machine trivial: the timer only ever asks "what is
 * the next entry".
 */
const buildPhases = (settings: TimerSettings): Phase[] => {
  const phases: Phase[] = [];
  for (let round = 1; round <= settings.rounds; round++) {
    phases.push({
      kind: "work",
      round,
      durationMs: settings.workSeconds * 1000,
    });
    // Nothing after the final work — the session is over, not resting.
    if (round === settings.rounds) break;
    if (settings.restSeconds > 0) {
      phases.push({ kind: "rest", round, durationMs: settings.restSeconds * 1000 });
    }
    if (settings.roundRestSeconds > 0) {
      phases.push({
        kind: "roundRest",
        round,
        durationMs: settings.roundRestSeconds * 1000,
      });
    }
  }
  return phases;
};

/** mm:ss of the second the countdown is currently in (ceil, not floor). */
const formatClock = (ms: number): string => {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
};

interface BeepSpec {
  frequency: number;
  durationMs: number;
  delayMs?: number;
}

/** Short tick in each of the last three seconds of a phase. */
const COUNTDOWN_TICK: BeepSpec[] = [{ frequency: 880, durationMs: 80 }];

const PHASE_START: Record<PhaseKind, BeepSpec[]> = {
  work: [{ frequency: 1046, durationMs: 150 }],
  rest: [{ frequency: 659, durationMs: 150 }],
  roundRest: [{ frequency: 784, durationMs: 150 }],
};

const SESSION_DONE: BeepSpec[] = [
  { frequency: 880, durationMs: 120 },
  { frequency: 1108, durationMs: 120, delayMs: 150 },
  { frequency: 1318, durationMs: 220, delayMs: 300 },
];

const playBeeps = (ctx: AudioContext, specs: BeepSpec[]) => {
  if (ctx.state === "suspended") {
    // Resume is fire-and-forget here: the beeps this call schedules may be
    // the ones that get dropped, the next ones land. The context is created
    // inside the Start tap, so by the first transition it is running.
    void ctx.resume();
  }
  for (const { frequency, durationMs, delayMs = 0 } of specs) {
    const start = ctx.currentTime + delayMs / 1000;
    const end = start + durationMs / 1000;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = frequency;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.3, start + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, end);
    osc.connect(gain).connect(ctx.destination);
    osc.start(start);
    osc.stop(end + 0.05);
  }
};

const PHASE_META: Record<PhaseKind, { label: string; color: string }> = {
  work: { label: "WORK", color: "var(--success)" },
  rest: { label: "REST", color: "var(--error)" },
  roundRest: { label: "ROUND REST", color: "var(--warning)" },
};

interface SettingRowProps {
  label: string;
  color: string;
  value: number;
  /** How the value reads on the left of the row ("00:20", "8×", "off"). */
  formatted: string;
  step: number;
  min: number;
  max: number;
  unit?: string;
  disabled: boolean;
  onChange: (value: number) => void;
}

/**
 * One colored setting row: what it is and how big it is on the left, the
 * app's usual stepper on the right. The input is draft-based — while typing,
 * the raw text stays put and only valid numbers apply (clamped), so clearing
 * the field does not fight the user; blur reverts to the applied value.
 */
const SettingRow = ({
  label,
  color,
  value,
  formatted,
  step,
  min,
  max,
  unit,
  disabled,
  onChange,
}: SettingRowProps) => {
  const [draft, setDraft] = useState<string | null>(null);

  const commit = (raw: string) => {
    const parsed = parseInt(raw, 10);
    if (Number.isFinite(parsed)) {
      onChange(Math.min(max, Math.max(min, parsed)));
    }
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "var(--space-3)",
        padding: "var(--space-3) var(--space-4)",
        background: "var(--bg-secondary)",
        borderRadius: "var(--radius-md)",
        borderLeft: `3px solid ${color}`,
        opacity: disabled ? 0.6 : 1,
      }}
    >
      <div style={{ flex: "1 1 auto", minWidth: 0 }}>
        <div
          style={{
            fontSize: "12px",
            fontWeight: 600,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--text-secondary)",
          }}
        >
          {label}
        </div>
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "20px",
            fontWeight: 600,
            color,
            marginTop: "2px",
          }}
        >
          {formatted}
        </div>
      </div>
      <div className="stepper" style={{ flexShrink: 0 }}>
        <button
          type="button"
          className="stepper__btn stepper__btn--start"
          disabled={disabled}
          aria-label={`Decrease ${label}`}
          onClick={() => onChange(Math.max(min, value - step))}
        >
          <Minus style={{ width: "18px", height: "18px" }} />
        </button>
        <input
          type="number"
          inputMode="numeric"
          className="input--stepper input--mono"
          aria-label={label}
          min={min}
          max={max}
          disabled={disabled}
          value={draft ?? String(value)}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
            setDraft(e.target.value);
            commit(e.target.value);
          }}
          onBlur={() => setDraft(null)}
        />
        <button
          type="button"
          className="stepper__btn stepper__btn--end"
          disabled={disabled}
          aria-label={`Increase ${label}`}
          onClick={() => onChange(Math.min(max, value + step))}
        >
          <Plus style={{ width: "18px", height: "18px" }} />
        </button>
        {unit && <span className="stepper__unit">{unit}</span>}
      </div>
    </div>
  );
};

const IntervalTimer = () => {
  const navigate = useNavigate();

  const [settings, setSettings] = useState<TimerSettings>(loadSettings);
  const [phases, setPhases] = useState<Phase[]>(() => buildPhases(settings));
  const [status, setStatus] = useState<Status>("idle");
  const [phaseIndex, setPhaseIndex] = useState(0);
  const [remainingMs, setRemainingMs] = useState(
    () => buildPhases(settings)[0].durationMs,
  );

  const endAtRef = useRef(0);
  const rafRef = useRef(0);
  const audioRef = useRef<AudioContext | null>(null);
  const lastTickSecondRef = useRef(-1);

  // Settings persist across visits, on this device only.
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      // Private mode or quota: the timer still works, it just does not remember.
    }
  }, [settings]);

  // The countdown loop. Runs only while `status === "running"`; pausing is
  // simply cancelling the frame, because the deadline lives in a ref and the
  // remainder in state.
  useEffect(() => {
    if (status !== "running") return;

    const tick = () => {
      const remaining = endAtRef.current - performance.now();

      if (remaining > 0) {
        setRemainingMs(remaining);

        const phase = phases[phaseIndex];
        const secondsLeft = Math.ceil(remaining / 1000);
        if (
          secondsLeft <= 3 &&
          secondsLeft * 1000 < phase.durationMs &&
          secondsLeft !== lastTickSecondRef.current
        ) {
          lastTickSecondRef.current = secondsLeft;
          if (audioRef.current) playBeeps(audioRef.current, COUNTDOWN_TICK);
        }

        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      // Phase boundary. The overshoot is carried into the next deadline so a
      // busy frame makes the session late once rather than drift every phase.
      const overshoot = -remaining;
      const nextIndex = phaseIndex + 1;
      if (nextIndex >= phases.length) {
        setRemainingMs(0);
        setStatus("done");
        if (audioRef.current) playBeeps(audioRef.current, SESSION_DONE);
        return;
      }
      const next = phases[nextIndex];
      endAtRef.current = performance.now() + next.durationMs - overshoot;
      lastTickSecondRef.current = -1;
      setPhaseIndex(nextIndex);
      setRemainingMs(next.durationMs - overshoot);
      if (audioRef.current) playBeeps(audioRef.current, PHASE_START[next.kind]);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [status, phaseIndex, phases]);

  // The AudioContext outlives the run it was created for (pause/resume reuse
  // it), so it is closed on unmount rather than on done.
  useEffect(() => {
    return () => {
      audioRef.current?.close().catch(() => undefined);
      audioRef.current = null;
    };
  }, []);

  /** Create/resume the context. Must be called from a user gesture. */
  const ensureAudio = (): AudioContext | null => {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Ctor) return null;
    if (!audioRef.current) audioRef.current = new Ctor();
    if (audioRef.current.state === "suspended") void audioRef.current.resume();
    return audioRef.current;
  };

  const handleStart = () => {
    const ctx = ensureAudio();
    const schedule = buildPhases(settings);
    setPhases(schedule);
    setPhaseIndex(0);
    lastTickSecondRef.current = -1;
    endAtRef.current = performance.now() + schedule[0].durationMs;
    setRemainingMs(schedule[0].durationMs);
    if (ctx) playBeeps(ctx, PHASE_START[schedule[0].kind]);
    setStatus("running");
  };

  const handleResume = () => {
    ensureAudio();
    endAtRef.current = performance.now() + remainingMs;
    setStatus("running");
  };

  const handlePause = () => setStatus("paused");

  const handleReset = () => {
    setStatus("idle");
    setPhaseIndex(0);
    lastTickSecondRef.current = -1;
    setRemainingMs(phases[0].durationMs);
  };

  // Reachable only while idle or done — the rows are disabled mid-run — so a
  // changed setting rebuilds the schedule rather than mutating a live session
  // out from under the countdown.
  const handleSettingsChange = (patch: Partial<TimerSettings>) => {
    const next = { ...settings, ...patch };
    const schedule = buildPhases(next);
    setSettings(next);
    setPhases(schedule);
    setPhaseIndex(0);
    lastTickSecondRef.current = -1;
    setRemainingMs(schedule[0].durationMs);
    setStatus("idle");
  };

  const isLive = status === "running" || status === "paused";
  const phase = phases[phaseIndex];

  const display =
    status === "done"
      ? { label: "DONE", color: "var(--accent)", clock: "00:00" }
      : status === "idle"
        ? { label: "READY", color: "var(--text-primary)", clock: formatClock(remainingMs) }
        : {
            label: PHASE_META[phase.kind].label,
            color: PHASE_META[phase.kind].color,
            clock: formatClock(remainingMs),
          };

  const formatSeconds = (seconds: number) => formatClock(seconds * 1000);

  return (
    <>
      <Navigation />
      <div className="page">
        <div className="page__content page__content--narrow">
          {/* Header */}
          <div
            className="flex items-center animate-in"
            style={{ gap: "var(--space-4)", marginBottom: "var(--space-6)" }}
          >
            <Button
              variant="secondary"
              size="icon"
              onClick={() => navigate(-1)}
              className="icon-btn"
              aria-label="Back"
            >
              <ArrowLeft style={{ width: "20px", height: "20px" }} />
            </Button>
            <div>
              <h1 className="page__title page__title--compact">
                INTERVAL TIMER
              </h1>
              <p className="page__subtitle">
                Work / rest rounds — settings stay on this device
              </p>
            </div>
          </div>

          {/* Countdown */}
          <Card
            className="animate-in"
            style={{
              border: `2px solid ${display.color}`,
              boxShadow: `0 0 32px color-mix(in srgb, ${display.color} 20%, transparent)`,
              transition: "border-color 0.3s ease, box-shadow 0.3s ease",
              marginBottom: "var(--space-6)",
            }}
          >
            <CardContent
              className="flex flex-col items-center"
              style={{
                padding: "var(--space-8) var(--space-5)",
                gap: "var(--space-2)",
              }}
            >
              <div
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: "15px",
                  fontWeight: 700,
                  letterSpacing: "0.2em",
                  color: display.color,
                  transition: "color 0.3s ease",
                }}
              >
                {display.label}
              </div>
              <div
                role="timer"
                aria-label={`${display.label}, round ${phase.round} of ${settings.rounds}`}
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "clamp(72px, 22vw, 128px)",
                  fontWeight: 700,
                  lineHeight: 1,
                  fontVariantNumeric: "tabular-nums",
                  color: display.color,
                  transition: "color 0.3s ease",
                }}
              >
                {display.clock}
              </div>
              <div style={{ fontSize: "14px", color: "var(--text-muted)" }}>
                {status === "done"
                  ? `${settings.rounds} round${settings.rounds !== 1 ? "s" : ""} complete`
                  : `Round ${phase.round} / ${settings.rounds}${status === "paused" ? " · Paused" : ""}`}
              </div>
            </CardContent>
          </Card>

          {/* Controls */}
          <div
            className="flex animate-in"
            style={{ gap: "var(--space-3)", marginBottom: "var(--space-6)" }}
          >
            {status === "running" ? (
              <Button size="lg" className="flex-1" onClick={handlePause}>
                <Pause style={{ width: "20px", height: "20px" }} />
                Pause
              </Button>
            ) : status === "paused" ? (
              <Button size="lg" className="flex-1" onClick={handleResume}>
                <Play style={{ width: "20px", height: "20px" }} />
                Resume
              </Button>
            ) : (
              <Button size="lg" className="flex-1" onClick={handleStart}>
                <Play style={{ width: "20px", height: "20px" }} />
                {status === "done" ? "Go again" : "Start"}
              </Button>
            )}
            <Button
              size="lg"
              variant="secondary"
              onClick={handleReset}
              disabled={status === "idle"}
            >
              <RotateCcw style={{ width: "20px", height: "20px" }} />
              Reset
            </Button>
          </div>

          {/* Settings */}
          <div
            className="stagger-children"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-3)",
            }}
          >
            <SettingRow
              label="Work"
              color="var(--success)"
              value={settings.workSeconds}
              formatted={formatSeconds(settings.workSeconds)}
              step={5}
              min={5}
              max={3600}
              unit="sec"
              disabled={isLive}
              onChange={(workSeconds) => handleSettingsChange({ workSeconds })}
            />
            <SettingRow
              label="Rest"
              color="var(--error)"
              value={settings.restSeconds}
              formatted={formatSeconds(settings.restSeconds)}
              step={5}
              min={0}
              max={3600}
              unit="sec"
              disabled={isLive}
              onChange={(restSeconds) => handleSettingsChange({ restSeconds })}
            />
            <SettingRow
              label="Rounds"
              color="var(--chart-3)"
              value={settings.rounds}
              formatted={`${settings.rounds}×`}
              step={1}
              min={1}
              max={99}
              disabled={isLive}
              onChange={(rounds) => handleSettingsChange({ rounds })}
            />
            <SettingRow
              label="Round rest"
              color="var(--warning)"
              value={settings.roundRestSeconds}
              formatted={
                settings.roundRestSeconds === 0
                  ? "off"
                  : formatSeconds(settings.roundRestSeconds)
              }
              step={5}
              min={0}
              max={3600}
              unit="sec"
              disabled={isLive}
              onChange={(roundRestSeconds) =>
                handleSettingsChange({ roundRestSeconds })
              }
            />
          </div>
        </div>
      </div>
    </>
  );
};

export default IntervalTimer;
