/**
 * When to record at full rate, and when to stop (plan 0024 §3).
 *
 * Pure logic over millisecond timestamps, no SDK, tested on the host. The
 * service feeds it events and acts on the transitions it returns.
 *
 * - Idle → Recording: worn, not on the charger, and `stillMinutesToStart`
 *   consecutive idle minutes whose movement stayed under `stillThresholdMg`.
 * - Recording → Idle: sustained walking (`walkSteps` within `walkWindowMs`),
 *   taken off for `unwornMs`, put on the charger, or `maxRecordingMs`.
 *
 * Rolling over in bed is deliberately not a stop: only walking is.
 * All time arithmetic is unsigned subtraction, so the 49.7-day wrap of a u32
 * millisecond clock is harmless.
 */

#pragma once

#include <cstddef>
#include <cstdint>

namespace SleepLog {

struct PolicyConfig {
    uint16_t stillMinutesToStart = 20;
    /// Largest sample-to-sample change in a minute that still counts as still.
    uint16_t stillThresholdMg    = 50;
    uint32_t walkSteps           = 100;
    uint32_t walkWindowMs        = 10u * 60u * 1000u;
    uint32_t unwornMs            = 5u * 60u * 1000u;
    uint32_t maxRecordingMs      = 14u * 60u * 60u * 1000u;
};

enum class Mode : uint8_t { IDLE = 0, RECORDING = 1 };

enum class Reason : uint8_t {
    NONE         = 0,
    STILL        = 1,  ///< started: still long enough
    WALKING      = 2,
    UNWORN       = 3,
    CHARGING     = 4,
    MAX_DURATION = 5,
    STARTUP      = 6,  ///< the service started (always idle)
    SHUTDOWN     = 7,  ///< the service is stopping
};

struct Transition {
    Mode   to;
    Reason reason;
};

class SleepPolicy {
public:
    explicit SleepPolicy(PolicyConfig config = {}) : mCfg(config) {}

    void onTouch(bool worn, uint32_t nowMs);
    void onCharging(bool connected, uint32_t nowMs);
    void onSteps(uint32_t count, uint32_t nowMs);
    /// One idle minute's movement summary. Ignored while recording.
    void onIdleMinute(uint16_t movementMg, uint32_t nowMs);

    /// When a transition is due: applies it, fills `out`, returns true.
    bool evaluate(uint32_t nowMs, Transition& out);

    Mode mode() const { return mMode; }
    uint16_t stillMinutes() const { return mStillMinutes; }
    const PolicyConfig& config() const { return mCfg; }

private:
    void enter(Mode m, uint32_t nowMs);
    uint32_t stepsInWindow(uint32_t nowMs) const;

    struct StepSample {
        uint32_t tMs;
        uint32_t count;
    };
    static constexpr size_t kStepRing = 64;

    PolicyConfig mCfg;
    Mode     mMode = Mode::IDLE;
    uint32_t mModeSinceMs = 0;

    bool     mWorn = false;
    uint32_t mUnwornSinceMs = 0;
    bool     mCharging = false;
    uint16_t mStillMinutes = 0;

    StepSample mSteps[kStepRing] {};
    size_t     mStepHead = 0;   ///< next slot to write
    size_t     mStepCount = 0;  ///< valid entries
};

} // namespace SleepLog
