/**
 * SleepLog service: an autostarted, headless background service that records
 * heart rate and wrist motion at full rate while you are (probably) asleep,
 * and writes it in 10-minute chunk files for Helf to fetch (plan 0024).
 *
 * Packed as a Glance (the only GUI-less app type), so the glances screen also
 * shows a one-line status tile. The tile is a view only: showing or hiding it
 * never starts, stops or changes a recording, and unlike the SDK's example
 * glances this service does not exit on EVENT_GLANCE_STOP.
 *
 * The decisions live in `SleepPolicy` and the encoding in `RecordWriter`, both
 * tested on the host. This class is the SDK plumbing around them and cannot be
 * tested off the watch, so it is kept free of decisions.
 */

#pragma once

#include <cstdint>
#include <ctime>
#include <memory>

#include "SDK/Glance/GlanceControl.hpp"
#include "SDK/Kernel/Kernel.hpp"
#include "SDK/SensorLayer/SensorConnection.hpp"
#include "SDK/SensorLayer/SensorDataBatch.hpp"

#include "RecordWriter.hpp"
#include "SleepPolicy.hpp"

class Service
{
public:
    explicit Service(SDK::Kernel& kernel);
    ~Service();

    void run();

private:
    class FileSink : public SleepLog::ByteSink {
    public:
        std::unique_ptr<SDK::Interface::IFile> file;
        bool write(const uint8_t* data, size_t size) override;
    };

    // Sensors
    void connectIdle();
    void connectRecording();
    void handleSensors(uint32_t handle, SDK::Sensor::DataBatch& batch);
    void onAccel(SDK::Sensor::DataBatch& batch);
    void foldIdleMinute(const SleepLog::AccelSample& s);

    // Mode
    void applyTransition(const SleepLog::Transition& t, uint32_t nowMs);

    // Files
    bool openChunk(uint32_t nowMs);
    void closeChunk();
    void rotateIfDue(uint32_t nowMs);
    void recoverPartials();
    void pruneOldDays();

    // Glance tile (status only)
    void onGlanceStart();
    void refreshGlance();
    void pushGlance();

    SDK::Kernel& mKernel;

    SDK::Sensor::Connection mAccel;
    SDK::Sensor::Connection mHr;
    SDK::Sensor::Connection mTouch;
    SDK::Sensor::Connection mSteps;
    SDK::Sensor::Connection mCharging;
    SDK::Sensor::Connection mMotion;

    SleepLog::SleepPolicy  mPolicy;
    FileSink               mSink;
    SleepLog::RecordWriter mWriter;
    char     mChunkPath[96] {};
    bool     mChunkOpen = false;
    uint32_t mChunkOpenedMs = 0;
    uint32_t mLastFlushMs = 0;

    // Idle-minute accumulator (1 Hz samples, folded per minute).
    uint32_t mMinuteStartMs = 0;
    uint16_t mMinuteSamples = 0;
    uint16_t mMinuteMaxDeltaMg = 0;
    int32_t  mMinuteSum[3] {};
    bool     mHavePrev = false;
    SleepLog::AccelSample mPrev {};

    // Glance tile. Built once, on the first EVENT_GLANCE_START.
    SDK::Glance::Form        mGlanceUI;
    SDK::Glance::ControlText mGlanceTitle;
    SDK::Glance::ControlText mGlanceValue;
    bool        mGlanceBuilt = false;
    bool        mGlanceVisible = false;
    std::time_t mRecordingSinceUtc = 0;

    static constexpr int16_t kTitleX = 18;
    static constexpr int16_t kTitleY = 0;
    static constexpr int16_t kTitleW = 205;
    static constexpr int16_t kTitleH = 30;
    static constexpr int16_t kValueX = 18;
    static constexpr int16_t kValueY = 32;
    static constexpr int16_t kValueW = 205;
    static constexpr int16_t kValueH = 30;

    static constexpr const char* kRoot = "Sleep";

    // Sensor rates, in the SDK's units: milliseconds.
    static constexpr float    kIdleAccelPeriodMs  = 1000.0f;   // 1 Hz
    static constexpr uint32_t kIdleAccelLatencyMs = 60000;     // one batch a minute
    static constexpr float    kRecAccelPeriodMs   = 20.0f;     // ~50 Hz
    static constexpr uint32_t kRecAccelLatencyMs  = 1000;
    static constexpr float    kHrPeriodMs         = 1000.0f;   // the sensor's minimum
    static constexpr uint32_t kHrLatencyMs        = 5000;
    static constexpr float    kStatePeriodMs      = 10000.0f;  // touch, steps
    static constexpr uint32_t kStateLatencyMs     = 30000;

    static constexpr uint32_t kRecChunkMs   = 10u * 60u * 1000u;
    static constexpr uint32_t kIdleChunkMs  = 6u * 60u * 60u * 1000u;
    static constexpr uint32_t kFlushMs      = 60u * 1000u;
    static constexpr uint32_t kLoopWaitMs   = 30u * 1000u;
    static constexpr uint32_t kKeepDays     = 14;
};
