import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  CirclePause,
  CirclePlay,
  Clock,
  Minus,
  Pause,
  Play,
  Plus,
  RotateCcw,
  RotateCw,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Navigation from "@/components/Navigation";
import { Button } from "@/components/ui/button";

/**
 * Client-side interval timer — a circuit of exercises, each a work interval
 * with rest between, repeated for a number of rounds. Modelled on a
 * minimalist HIIT timer: one big countdown, phase-colored, five setting rows.
 * Opened from the day view.
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
 * timer the user is looking at. A screen wake lock is held while running so
 * the phone does not sleep — and so stop the loop — mid-session.
 */

interface TimerSettings {
  workSeconds: number;
  restSeconds: number;
  /** Work intervals per round. */
  exercises: number;
  rounds: number;
  /**
   * The gap between rounds, in place of the ordinary rest. 0 = off, and the
   * ordinary rest is used there too. The storage name predates the "Round
   * Reset" label and is kept so saved settings still load.
   */
  roundRestSeconds: number;
}

type PhaseKind = "work" | "rest" | "roundRest";

interface Phase {
  kind: PhaseKind;
  /** 1-based round and exercise; a rest shares the work it follows. */
  round: number;
  exercise: number;
  /** Set on the round's final work (and the gap after it): its end is the round's. */
  lastOfRound: boolean;
  durationMs: number;
}

type Status = "idle" | "running" | "paused" | "done";

const STORAGE_KEY = "helf-interval-timer-settings";

const DEFAULT_SETTINGS: TimerSettings = {
  workSeconds: 20,
  restSeconds: 10,
  exercises: 5,
  rounds: 2,
  roundRestSeconds: 10,
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
      // Absent from settings saved before the field existed, when every round
      // was a single work interval. Falling back to 1 replays those unchanged.
      exercises: clampInt(parsed.exercises, 1, 50, 1),
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
 * The schedule as an explicit list: within a round, one work phase per
 * exercise with rests between; between rounds, the round reset (or the rest,
 * when the reset is off). Nothing follows the final work — the session is
 * over, not resting. Building it as a list — rather than computing the phase
 * from elapsed time — is what keeps the state machine trivial: the timer only
 * ever asks "what is the next entry".
 */
const buildPhases = (settings: TimerSettings): Phase[] => {
  const phases: Phase[] = [];
  for (let round = 1; round <= settings.rounds; round++) {
    for (let exercise = 1; exercise <= settings.exercises; exercise++) {
      const lastOfRound = exercise === settings.exercises;
      phases.push({
        kind: "work",
        round,
        exercise,
        lastOfRound,
        durationMs: settings.workSeconds * 1000,
      });
      if (lastOfRound && round === settings.rounds) break;
      if (lastOfRound && settings.roundRestSeconds > 0) {
        phases.push({
          kind: "roundRest",
          round,
          exercise,
          lastOfRound,
          durationMs: settings.roundRestSeconds * 1000,
        });
      } else if (settings.restSeconds > 0) {
        phases.push({
          kind: "rest",
          round,
          exercise,
          lastOfRound,
          durationMs: settings.restSeconds * 1000,
        });
      }
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
  type?: OscillatorType;
  /** Peak level, 0–1. */
  gain?: number;
}

/*
 * The sounds are meant to be read without looking at the phone, so each cue
 * differs in shape as well as pitch — a long tone, a falling pair, a bell, a
 * rising run — and none is a variant of another:
 *
 *   pip pip pip   last three seconds of any phase; high before work starts
 *                 ("get ready"), low before work stops ("nearly there")
 *   GO            work starts: one long bright tone, the loudest cue
 *   fall          rest starts: two soft notes stepping down
 *   ding-ding     a round ends, then one tap per round done (2 taps = round 2
 *                 finished), so the count is audible too
 *   rising run    the session is over
 *
 * The end of a round replaces the rest cue that would otherwise sound there,
 * so the bell always means "round over" whichever gap follows it.
 */

/** Before work starts — the pips climb towards GO. */
const PIP_BEFORE_WORK: BeepSpec[] = [{ frequency: 988, durationMs: 70, gain: 0.25 }];
/** Before work stops. */
const PIP_BEFORE_REST: BeepSpec[] = [{ frequency: 698, durationMs: 70, gain: 0.25 }];

const COUNTDOWN_PIP: Record<PhaseKind, BeepSpec[]> = {
  work: PIP_BEFORE_REST,
  rest: PIP_BEFORE_WORK,
  roundRest: PIP_BEFORE_WORK,
};

const WORK_START: BeepSpec[] = [
  { frequency: 1319, durationMs: 450, type: "triangle", gain: 0.5 },
  { frequency: 659, durationMs: 450, gain: 0.3 },
];

const REST_START: BeepSpec[] = [
  { frequency: 784, durationMs: 160, gain: 0.35 },
  { frequency: 587, durationMs: 280, delayMs: 180, gain: 0.35 },
];

const BELL_STRIKE = (delayMs: number): BeepSpec[] => [
  { frequency: 1047, durationMs: 500, delayMs, gain: 0.4 },
  // An octave overtone, quieter, is what makes a sine read as a bell.
  { frequency: 2093, durationMs: 250, delayMs, gain: 0.12 },
];

/** Past this many rounds the taps stop being countable by ear. */
const MAX_COUNTED_ROUNDS = 10;

const roundEndSound = (round: number, totalRounds: number): BeepSpec[] => {
  const sound = [...BELL_STRIKE(0), ...BELL_STRIKE(260)];
  if (totalRounds <= MAX_COUNTED_ROUNDS) {
    for (let i = 0; i < round; i++) {
      sound.push({
        frequency: 440,
        durationMs: 45,
        delayMs: 900 + i * 150,
        type: "square",
        gain: 0.15,
      });
    }
  }
  return sound;
};

const SESSION_DONE: BeepSpec[] = [
  { frequency: 880, durationMs: 120, gain: 0.4 },
  { frequency: 1108, durationMs: 120, delayMs: 150, gain: 0.4 },
  { frequency: 1318, durationMs: 120, delayMs: 300, gain: 0.4 },
  { frequency: 1760, durationMs: 600, delayMs: 450, gain: 0.45 },
];

/** When the last note of a sound finishes, in ms from its start. */
const soundLength = (specs: BeepSpec[]) =>
  Math.max(...specs.map(({ durationMs, delayMs = 0 }) => delayMs + durationMs));

const delayed = (specs: BeepSpec[], byMs: number): BeepSpec[] =>
  specs.map((spec) => ({ ...spec, delayMs: (spec.delayMs ?? 0) + byMs }));

/** The cue for moving from `prev` into `next`. */
const boundarySound = (prev: Phase, next: Phase, totalRounds: number): BeepSpec[] => {
  if (prev.kind === "work" && prev.lastOfRound) {
    const roundEnd = roundEndSound(prev.round, totalRounds);
    // With no rest and no reset between rounds, the next work starts at
    // once; GO waits for the bell and the count rather than talking over them.
    return next.kind === "work"
      ? [...roundEnd, ...delayed(WORK_START, soundLength(roundEnd) + 100)]
      : roundEnd;
  }
  return next.kind === "work" ? WORK_START : REST_START;
};

const playBeeps = (ctx: AudioContext, specs: BeepSpec[]) => {
  if (ctx.state === "suspended") {
    // Resume is fire-and-forget here: the beeps this call schedules may be
    // the ones that get dropped, the next ones land. The context is created
    // inside the Start tap, so by the first transition it is running.
    void ctx.resume();
  }
  for (const {
    frequency,
    durationMs,
    delayMs = 0,
    type = "sine",
    gain: peak = 0.3,
  } of specs) {
    const start = ctx.currentTime + delayMs / 1000;
    const end = start + durationMs / 1000;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = frequency;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(peak, start + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, end);
    osc.connect(gain).connect(ctx.destination);
    osc.start(start);
    osc.stop(end + 0.05);
  }
};

/**
 * Hero colours. The hero is a solid colour under a fixed light-to-dark
 * overlay, so a phase change is a `background-color` transition — gradients
 * themselves do not animate. Idle is the coral of the timer this is modelled
 * on, deliberately not the rest red, so READY never reads as a rest.
 */
const HERO_COLOR = {
  idle: "#e2504f",
  work: "#16a34a",
  rest: "#dc2626",
  roundRest: "#ca8a04",
  done: "#ea580c",
} as const;

const PHASE_LABEL: Record<PhaseKind, string> = {
  work: "WORK",
  rest: "REST",
  roundRest: "ROUND RESET",
};

type SettingKey = keyof TimerSettings;

interface SettingSpec {
  key: SettingKey;
  label: string;
  icon: LucideIcon;
  color: string;
  step: number;
  min: number;
  max: number;
  unit?: string;
  format: (value: number) => string;
}

const formatSeconds = (seconds: number) => formatClock(seconds * 1000);

const SETTING_SPECS: SettingSpec[] = [
  {
    key: "workSeconds",
    label: "Work",
    icon: CirclePlay,
    color: "var(--success)",
    step: 5,
    min: 5,
    max: 3600,
    unit: "sec",
    format: formatSeconds,
  },
  {
    key: "restSeconds",
    label: "Rest",
    icon: CirclePause,
    color: "var(--error)",
    step: 5,
    min: 0,
    max: 3600,
    unit: "sec",
    format: formatSeconds,
  },
  {
    key: "exercises",
    label: "Exercises",
    icon: Zap,
    color: "var(--text-secondary)",
    step: 1,
    min: 1,
    max: 50,
    format: String,
  },
  {
    key: "rounds",
    label: "Rounds",
    icon: RotateCw,
    color: "#818cf8",
    step: 1,
    min: 1,
    max: 99,
    format: (rounds) => `${rounds}X`,
  },
  {
    key: "roundRestSeconds",
    label: "Round Reset",
    icon: Clock,
    color: "var(--warning)",
    step: 5,
    min: 0,
    max: 3600,
    unit: "sec",
    format: (seconds) => (seconds === 0 ? "Off" : formatSeconds(seconds)),
  },
];

interface SettingRowProps {
  spec: SettingSpec;
  value: number;
  open: boolean;
  disabled: boolean;
  onToggle: () => void;
  onChange: (value: number) => void;
}

/**
 * One tinted setting row: icon, name, value. Tapping it opens the app's
 * usual stepper underneath. The input is draft-based — while typing, the raw
 * text stays put and only valid numbers apply (clamped), so clearing the field
 * does not fight the user; blur reverts to the applied value.
 */
const SettingRow = ({
  spec,
  value,
  open,
  disabled,
  onToggle,
  onChange,
}: SettingRowProps) => {
  const { key, label, icon: Icon, color, step, min, max, unit } = spec;
  const [draft, setDraft] = useState<string | null>(null);
  const editorId = `timer-setting-${key}`;

  const commit = (raw: string) => {
    const parsed = parseInt(raw, 10);
    if (Number.isFinite(parsed)) {
      onChange(Math.min(max, Math.max(min, parsed)));
    }
  };

  return (
    <div
      className="timer-setting"
      style={{ "--setting-color": color } as React.CSSProperties}
    >
      <button
        type="button"
        className="timer-setting__row"
        aria-label={`${label} ${spec.format(value)}`}
        aria-expanded={open}
        aria-controls={editorId}
        disabled={disabled}
        onClick={onToggle}
      >
        <Icon className="timer-setting__icon" />
        <span className="timer-setting__label">{label}</span>
        <span className="timer-setting__value">{spec.format(value)}</span>
      </button>
      {open && (
        <div id={editorId} className="timer-setting__editor">
          <div className="stepper">
            <button
              type="button"
              className="stepper__btn stepper__btn--start"
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
              aria-label={`Increase ${label}`}
              onClick={() => onChange(Math.min(max, value + step))}
            >
              <Plus style={{ width: "18px", height: "18px" }} />
            </button>
            {unit && <span className="stepper__unit">{unit}</span>}
          </div>
        </div>
      )}
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
  const [openSetting, setOpenSetting] = useState<SettingKey | null>(null);

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
          if (audioRef.current) playBeeps(audioRef.current, COUNTDOWN_PIP[phase.kind]);
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
      const prev = phases[phaseIndex];
      const next = phases[nextIndex];
      endAtRef.current = performance.now() + next.durationMs - overshoot;
      lastTickSecondRef.current = -1;
      setPhaseIndex(nextIndex);
      setRemainingMs(next.durationMs - overshoot);
      if (audioRef.current) {
        const totalRounds = phases[phases.length - 1].round;
        playBeeps(audioRef.current, boundarySound(prev, next, totalRounds));
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [status, phaseIndex, phases]);

  // Keep the screen on while running. A sleeping phone stops the rAF loop and
  // with it the beeps. The OS drops the lock whenever the page is hidden, so
  // it is re-requested on return. Best effort: unsupported or refused just
  // means the screen may sleep.
  useEffect(() => {
    if (status !== "running" || !("wakeLock" in navigator)) return;
    let lock: WakeLockSentinel | null = null;
    let cancelled = false;

    const acquire = () => {
      if (document.visibilityState !== "visible") return;
      navigator.wakeLock
        .request("screen")
        .then((sentinel) => {
          if (cancelled) void sentinel.release();
          else lock = sentinel;
        })
        .catch(() => undefined);
    };

    acquire();
    document.addEventListener("visibilitychange", acquire);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", acquire);
      void lock?.release().catch(() => undefined);
    };
  }, [status]);

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
    setOpenSetting(null);
    setPhases(schedule);
    setPhaseIndex(0);
    lastTickSecondRef.current = -1;
    endAtRef.current = performance.now() + schedule[0].durationMs;
    setRemainingMs(schedule[0].durationMs);
    if (ctx) playBeeps(ctx, WORK_START);
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
  const totalMs = phases.reduce((sum, p) => sum + p.durationMs, 0);
  const sessionLeftMs =
    remainingMs +
    phases.slice(phaseIndex + 1).reduce((sum, p) => sum + p.durationMs, 0);

  // Idle shows the whole session's length, the way the screenshot's 04:50 is
  // 5 × 20s work + 4 × 10s rest, twice, plus one 10s reset. Running shows the
  // phase, with the session's remainder underneath.
  const display =
    status === "done"
      ? {
          label: "DONE",
          color: HERO_COLOR.done,
          clock: "00:00",
          detail: `${settings.rounds} round${settings.rounds !== 1 ? "s" : ""} complete`,
        }
      : status === "idle"
        ? {
            label: "READY",
            color: HERO_COLOR.idle,
            clock: formatClock(totalMs),
            detail: `${settings.exercises} exercise${settings.exercises !== 1 ? "s" : ""} × ${settings.rounds} round${settings.rounds !== 1 ? "s" : ""}`,
          }
        : {
            label: PHASE_LABEL[phase.kind],
            color: HERO_COLOR[phase.kind],
            clock: formatClock(remainingMs),
            detail: `Exercise ${phase.exercise} / ${settings.exercises} · Round ${phase.round} / ${settings.rounds}${status === "paused" ? " · Paused" : ` · ${formatClock(sessionLeftMs)} left`}`,
          };

  // One button that plays, pauses and resumes, as on the timer this is
  // modelled on.
  const handlePrimary = () => {
    if (status === "running") handlePause();
    else if (status === "paused") handleResume();
    else handleStart();
  };
  const primaryLabel =
    status === "running"
      ? "Pause"
      : status === "paused"
        ? "Resume"
        : status === "done"
          ? "Go again"
          : "Start";
  const PrimaryIcon = status === "running" ? Pause : Play;

  return (
    <>
      <Navigation />
      <div className="page">
        <div className="page__content">
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
                Work / rest circuits — settings stay on this device
              </p>
            </div>
          </div>

          <div className="interval-timer animate-in">
            {/* Countdown */}
            <div
              className="timer-hero"
              style={{ backgroundColor: display.color }}
            >
              <div className="timer-hero__label">{display.label}</div>
              <div
                role="timer"
                aria-label={
                  isLive
                    ? `${display.label}, exercise ${phase.exercise} of ${settings.exercises}, round ${phase.round} of ${settings.rounds}`
                    : display.label
                }
                className="timer-hero__clock"
              >
                {display.clock}
              </div>
              <div className="timer-hero__detail">{display.detail}</div>
            </div>

            {/* Controls: the play button sits in a notch on the hero's edge. */}
            <div className="timer-controls">
              <button
                type="button"
                className="timer-play"
                style={{ color: display.color }}
                onClick={handlePrimary}
                aria-label={primaryLabel}
              >
                <PrimaryIcon
                  className="timer-play__icon"
                  fill="currentColor"
                  // A triangle's visual centre sits right of its box's.
                  style={PrimaryIcon === Play ? { marginLeft: "4px" } : undefined}
                />
              </button>
              {status !== "idle" && (
                <button
                  type="button"
                  className="timer-reset"
                  onClick={handleReset}
                  aria-label="Reset"
                >
                  <RotateCcw style={{ width: "20px", height: "20px" }} />
                </button>
              )}
            </div>

            {/* Settings */}
            <div className="timer-settings">
              {SETTING_SPECS.map((spec) => (
                <SettingRow
                  key={spec.key}
                  spec={spec}
                  value={settings[spec.key]}
                  open={openSetting === spec.key && !isLive}
                  disabled={isLive}
                  onToggle={() =>
                    setOpenSetting((current) =>
                      current === spec.key ? null : spec.key,
                    )
                  }
                  onChange={(value) =>
                    handleSettingsChange({ [spec.key]: value })
                  }
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default IntervalTimer;
