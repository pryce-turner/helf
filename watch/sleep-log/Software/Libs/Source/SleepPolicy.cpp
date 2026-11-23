#include "SleepPolicy.hpp"

namespace SleepLog {

void SleepPolicy::onTouch(bool worn, uint32_t nowMs)
{
    if (mWorn && !worn) mUnwornSinceMs = nowMs;
    mWorn = worn;
    // Taken off resets the stillness count: a watch on the nightstand is
    // perfectly still and must never start a recording.
    if (!worn) mStillMinutes = 0;
}

void SleepPolicy::onCharging(bool connected, uint32_t nowMs)
{
    (void)nowMs;
    mCharging = connected;
    if (connected) mStillMinutes = 0;
}

void SleepPolicy::onSteps(uint32_t count, uint32_t nowMs)
{
    mSteps[mStepHead] = {nowMs, count};
    mStepHead = (mStepHead + 1) % kStepRing;
    if (mStepCount < kStepRing) ++mStepCount;
}

void SleepPolicy::onIdleMinute(uint16_t movementMg, uint32_t nowMs)
{
    (void)nowMs;
    if (mMode != Mode::IDLE) return;
    if (mWorn && !mCharging && movementMg < mCfg.stillThresholdMg) {
        if (mStillMinutes < 0xFFFF) ++mStillMinutes;
    } else {
        mStillMinutes = 0;
    }
}

uint32_t SleepPolicy::stepsInWindow(uint32_t nowMs) const
{
    // Steps since the oldest sample still inside the window. The counter is
    // monotonic since boot, so a difference of two readings is the count; a
    // reboot resets it, which can only make this smaller, never larger.
    if (mStepCount == 0) return 0;
    const size_t newest = (mStepHead + kStepRing - 1) % kStepRing;
    uint32_t oldestCount = mSteps[newest].count;
    for (size_t k = 0; k < mStepCount; ++k) {
        const StepSample& s = mSteps[(newest + kStepRing - k) % kStepRing];
        if (nowMs - s.tMs > mCfg.walkWindowMs) break;
        // Also ignore anything from before this recording began.
        if (s.tMs - mModeSinceMs > nowMs - mModeSinceMs) break;
        oldestCount = s.count;
    }
    const uint32_t latest = mSteps[newest].count;
    return latest >= oldestCount ? latest - oldestCount : 0;
}

void SleepPolicy::enter(Mode m, uint32_t nowMs)
{
    mMode = m;
    mModeSinceMs = nowMs;
    mStillMinutes = 0;
}

bool SleepPolicy::evaluate(uint32_t nowMs, Transition& out)
{
    if (mMode == Mode::IDLE) {
        if (mWorn && !mCharging && mStillMinutes >= mCfg.stillMinutesToStart) {
            enter(Mode::RECORDING, nowMs);
            out = {Mode::RECORDING, Reason::STILL};
            return true;
        }
        return false;
    }

    Reason why = Reason::NONE;
    if (mCharging) {
        why = Reason::CHARGING;
    } else if (!mWorn && nowMs - mUnwornSinceMs >= mCfg.unwornMs) {
        why = Reason::UNWORN;
    } else if (stepsInWindow(nowMs) >= mCfg.walkSteps) {
        why = Reason::WALKING;
    } else if (nowMs - mModeSinceMs >= mCfg.maxRecordingMs) {
        why = Reason::MAX_DURATION;
    }
    if (why == Reason::NONE) return false;
    enter(Mode::IDLE, nowMs);
    out = {Mode::IDLE, why};
    return true;
}

} // namespace SleepLog
