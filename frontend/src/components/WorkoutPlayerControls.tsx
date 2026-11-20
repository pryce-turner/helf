import { Pause, Play, RotateCcw, SkipForward, Square, Check, AlertTriangle } from "lucide-react";
import { formatSeconds } from "@/lib/setTiles";
import type { PlayerStatus } from "@/hooks/useWorkoutPlayer";

/**
 * The day player's readout and controls, shown in place of the day's header
 * actions while a run is live (plan 0018). One primary button that pauses
 * and resumes, a Stop that saves actuals through the instant, a Complete
 * set for untimed tiles the player will not invent a duration for, and a
 * Retry when a write failed — a run must never claim unsaved work reached
 * the log.
 */

interface WorkoutPlayerControlsProps {
    status: PlayerStatus;
    phaseKind: "getReady" | "work" | "rest" | "restAfter" | "manual" | null;
    exerciseName: string | null;
    progressLabel: string;
    remainingMs: number;
    onPause: () => void;
    onResume: () => void;
    onStop: () => void;
    onCompleteSet: () => void;
    onRetry: () => void;
    onCancel: () => void;
    onRestartPhase: () => void;
    onSkipPhase: () => void;
}

const PHASE_LABEL: Record<string, string> = {
    getReady: "GET READY",
    work: "WORK",
    rest: "REST",
    restAfter: "REST AFTER SET",
    manual: "YOUR SET",
};

const HERO_COLOR: Record<string, string> = {
    getReady: "#2563eb",
    work: "#16a34a",
    rest: "#dc2626",
    restAfter: "#ca8a04",
    manual: "#7c3aed",
};

const WorkoutPlayerControls = ({
    status,
    phaseKind,
    exerciseName,
    progressLabel,
    remainingMs,
    onPause,
    onResume,
    onStop,
    onCompleteSet,
    onRetry,
    onCancel,
    onRestartPhase,
    onSkipPhase,
}: WorkoutPlayerControlsProps) => {

    if (status === "error") {
        return (
            <div className="player-wrap animate-in">
                <div
                    className="player-hero"
                    style={{ backgroundColor: "var(--error)" }}
                    role="alert"
                >
                    <div className="timer-hero__label">
                        <AlertTriangle
                            style={{ width: "16px", height: "16px", verticalAlign: "-3px" }}
                        />{" "}
                        NOT SAVED
                    </div>
                    <div className="timer-hero__detail">
                        The write for the set you just finished failed. Nothing
                        has moved on — retry to log it and continue, or discard
                        the run and leave the set planned.
                    </div>
                </div>
                <div className="timer-controls">
                    <button
                        type="button"
                        className="timer-play"
                        style={{ color: "var(--error)" }}
                        onClick={onRetry}
                        aria-label="Retry saving"
                    >
                        <Play className="timer-play__icon" fill="currentColor" style={{ marginLeft: "4px" }} />
                    </button>
                    <button
                        type="button"
                        className="timer-reset"
                        onClick={onCancel}
                        aria-label="Discard the run"
                        title="Discard — leave the set planned and return to the day"
                    >
                        <Square style={{ width: "18px", height: "18px" }} />
                    </button>
                </div>
            </div>
        );
    }

    if (status === "done") {
        return (
            <div className="player-wrap animate-in">
                <div className="player-hero" style={{ backgroundColor: "#ea580c" }}>
                    <div className="timer-hero__label">DONE</div>
                    <div className="timer-hero__detail">
                        The run is over and every write landed.
                    </div>
                </div>
            </div>
        );
    }

    const color = HERO_COLOR[phaseKind ?? "work"] ?? HERO_COLOR.work;
    const paused = status === "paused";

    return (
        <div className="player-wrap animate-in">
            <div className="player-hero" style={{ backgroundColor: color }}>
                <div className="timer-hero__label">{PHASE_LABEL[phaseKind ?? "work"]}</div>
                {phaseKind !== "manual" && (
                    <div role="timer" aria-label={progressLabel} className="timer-hero__clock">
                        {formatSeconds(Math.max(0, remainingMs / 1000))}
                    </div>
                )}
                <div className="timer-hero__detail">
                    {exerciseName ? `${exerciseName} · ` : ""}
                    {progressLabel}
                    {paused ? " · Paused" : ""}
                </div>
            </div>
            <div className="timer-controls">
                {phaseKind === "manual" ? (
                    <button
                        type="button"
                        className="timer-play"
                        style={{ color }}
                        onClick={onCompleteSet}
                        aria-label="Complete set"
                    >
                        <Check className="timer-play__icon" />
                    </button>
                ) : (
                    <>
                        {/* Restart re-arms the current phase at full; Skip
                            ends it now and banks partial — a skipped rep is
                            a partial rep, never a full one. */}
                        <button
                            type="button"
                            className="timer-skip"
                            onClick={onRestartPhase}
                            aria-label="Restart timer"
                            title="Restart this phase at full"
                        >
                            <RotateCcw style={{ width: "18px", height: "18px" }} />
                        </button>
                        <button
                            type="button"
                            className="timer-play"
                            style={{ color }}
                            onClick={paused ? onResume : onPause}
                            aria-label={paused ? "Resume" : "Pause"}
                        >
                            {paused ? (
                                <Play className="timer-play__icon" fill="currentColor" style={{ marginLeft: "4px" }} />
                            ) : (
                                <Pause className="timer-play__icon" fill="currentColor" />
                            )}
                        </button>
                        <button
                            type="button"
                            className="timer-skip"
                            onClick={onSkipPhase}
                            aria-label="Skip to next timer"
                            title="End this phase and move on"
                            disabled={paused}
                        >
                            <SkipForward style={{ width: "18px", height: "18px" }} />
                        </button>
                    </>
                )}
                <button
                    type="button"
                    className="timer-reset"
                    onClick={onStop}
                    aria-label="Stop"
                    title="Stop — saves what was actually done"
                >
                    <Square style={{ width: "18px", height: "18px" }} fill="currentColor" />
                </button>
            </div>
        </div>
    );
};

export default WorkoutPlayerControls;
