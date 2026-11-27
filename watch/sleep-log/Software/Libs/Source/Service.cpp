#include "Service.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>

#define LOG_MODULE_PRX      "SleepLog"
#define LOG_MODULE_LEVEL    LOG_LEVEL_INFO
#include "SDK/UnaLogger/Logger.h"

#include "SDK/Messages/CommandMessages.hpp"
#include "SDK/Messages/MessageGuard.hpp"
#include "SDK/Messages/SensorLayerMessages.hpp"
#include "SDK/SensorLayer/DataParsers/SensorDataParserAccelerometer.hpp"
#include "SDK/SensorLayer/DataParsers/SensorDataParserBatteryCharging.hpp"
#include "SDK/SensorLayer/DataParsers/SensorDataParserHeartRate.hpp"
#include "SDK/SensorLayer/DataParsers/SensorDataParserMotionDetect.hpp"
#include "SDK/SensorLayer/DataParsers/SensorDataParserStepCounter.hpp"
#include "SDK/SensorLayer/DataParsers/SensorDataParserTouch.hpp"

using SleepLog::AccelSample;
using SleepLog::Mode;
using SleepLog::Reason;
using SleepLog::Transition;

namespace {

constexpr float kStandardGravity = 9.80665f;

/// m/s² (gravity included) → milli-g, clamped to an i16.
int16_t toMilliG(float ms2)
{
    const float mg = ms2 / kStandardGravity * 1000.0f;
    return static_cast<int16_t>(std::max(-32768.0f, std::min(32767.0f, std::round(mg))));
}

int32_t utcOffsetSeconds(std::time_t utc)
{
    std::tm local {};
    std::tm gm {};
    localtime_r(&utc, &local);
    gmtime_r(&utc, &gm);
    // Difference of the two broken-down times, as seconds within ±1 day.
    int32_t diff = (local.tm_hour - gm.tm_hour) * 3600 + (local.tm_min - gm.tm_min) * 60;
    const int dayDiff = local.tm_yday - gm.tm_yday;
    if (dayDiff == 1 || dayDiff < -1) diff += 86400;
    if (dayDiff == -1 || dayDiff > 1) diff -= 86400;
    return diff;
}

} // namespace

bool Service::FileSink::write(const uint8_t* data, size_t size)
{
    if (!file) return false;
    size_t written = 0;
    return file->write(reinterpret_cast<const char*>(data), size, written) && written == size;
}

Service::Service(SDK::Kernel& kernel)
    : mKernel(kernel)
    , mAccel(SDK::Sensor::Type::ACCELEROMETER, kIdleAccelPeriodMs, kIdleAccelLatencyMs)
    , mHr(SDK::Sensor::Type::HEART_RATE, kHrPeriodMs, kHrLatencyMs)
    // Periodic, not only on change: a watch already worn when the service
    // starts must still report it, or the policy never sees "worn".
    , mTouch(SDK::Sensor::Type::TOUCH_DETECT, kStatePeriodMs, kStateLatencyMs)
    , mSteps(SDK::Sensor::Type::STEP_COUNTER, kStatePeriodMs, kStateLatencyMs)
    , mCharging(SDK::Sensor::Type::BATTERY_CHARGING)
    , mMotion(SDK::Sensor::Type::MOTION_DETECT)
    , mWriter(mSink)
{
}

Service::~Service()
{
    closeChunk();
}

// ------------------------------------------------------------------ sensors

// The accelerometer stays connected in both modes, at a different rate. The
// SDK's Connection::connect(period, latency) returns without doing anything
// when already connected, so a rate change is a disconnect and a connect.
// Calling connect() alone kept the first night's recording at the idle 1 Hz
// (plan 0024 §9).

void Service::connectIdle()
{
    // HR off: holding it keeps the optical sensor on continuously
    // (SensorBody.cpp: a subscriber forces AUTO mode), which is the
    // recording's whole cost. Idle relies on the kernel's own bursts.
    mHr.disconnect();
    mAccel.disconnect();
    mAccel.connect(kIdleAccelPeriodMs, kIdleAccelLatencyMs);
    mHavePrev = false;
    mMinuteSamples = 0;
}

void Service::connectRecording()
{
    mAccel.disconnect();
    mAccel.connect(kRecAccelPeriodMs, kRecAccelLatencyMs);
    mHr.disconnect();
    mHr.connect(kHrPeriodMs, kHrLatencyMs);
}

void Service::handleSensors(uint32_t handle, SDK::Sensor::DataBatch& batch)
{
    if (mAccel.matchesDriver(handle)) {
        onAccel(batch);
        return;
    }
    for (uint16_t i = 0; i < batch.size(); ++i) {
        if (mHr.matchesDriver(handle)) {
            SDK::SensorDataParser::HeartRate p(batch[i]);
            if (p.isDataValid()) mWriter.hr(p.getTimestamp(), p.getBpm(), p.getTrustLevel());
        } else if (mTouch.matchesDriver(handle)) {
            SDK::SensorDataParser::Touch p(batch[i]);
            if (!p.isDataValid()) continue;
            mPolicy.onTouch(p.isTouched(), p.getTimestamp());
            mWriter.touch(p.getTimestamp(), p.isTouched());
        } else if (mSteps.matchesDriver(handle)) {
            SDK::SensorDataParser::StepCounter p(batch[i]);
            if (!p.isDataValid()) continue;
            mPolicy.onSteps(p.getStepCount(), p.getTimestamp());
            mWriter.steps(p.getTimestamp(), p.getStepCount());
        } else if (mCharging.matchesDriver(handle)) {
            SDK::SensorDataParser::BatteryCharging p(batch[i]);
            if (!p.isDataValid()) continue;
            mPolicy.onCharging(p.isUsbConnected(), p.getTimestamp());
            mWriter.charging(p.getTimestamp(), p.isUsbConnected(), p.isCharging());
        } else if (mMotion.matchesDriver(handle)) {
            SDK::SensorDataParser::MotionDetect p(batch[i]);
            if (p.isDataValid()) mWriter.motion(p.getTimestamp(), static_cast<uint8_t>(p.getID()));
        }
    }
}

void Service::onAccel(SDK::Sensor::DataBatch& batch)
{
    static constexpr uint16_t kChunk = 64;
    AccelSample samples[kChunk];
    uint16_t n = 0;

    for (uint16_t i = 0; i < batch.size(); ++i) {
        SDK::SensorDataParser::Accelerometer p(batch[i]);
        if (!p.isDataValid()) continue;
        const AccelSample s {p.getTimestamp(), toMilliG(p.getX()), toMilliG(p.getY()), toMilliG(p.getZ())};

        if (mPolicy.mode() == Mode::RECORDING) {
            samples[n++] = s;
            if (n == kChunk) {
                mWriter.accel(samples, n);
                n = 0;
            }
        } else {
            foldIdleMinute(s);
        }
    }
    if (n) mWriter.accel(samples, n);
}

void Service::foldIdleMinute(const AccelSample& s)
{
    if (mMinuteSamples == 0) {
        mMinuteStartMs = s.tMs;
        mMinuteMaxDeltaMg = 0;
        mMinuteSum[0] = mMinuteSum[1] = mMinuteSum[2] = 0;
    }
    if (mHavePrev) {
        const float dx = float(s.x - mPrev.x), dy = float(s.y - mPrev.y), dz = float(s.z - mPrev.z);
        const float d = std::sqrt(dx * dx + dy * dy + dz * dz);
        mMinuteMaxDeltaMg = static_cast<uint16_t>(std::min(65535.0f, std::max(float(mMinuteMaxDeltaMg), d)));
    }
    mPrev = s;
    mHavePrev = true;
    mMinuteSum[0] += s.x;
    mMinuteSum[1] += s.y;
    mMinuteSum[2] += s.z;
    ++mMinuteSamples;

    if (s.tMs - mMinuteStartMs >= 60000u) {
        const int32_t k = mMinuteSamples;
        mWriter.minute(s.tMs, mMinuteSamples, mMinuteMaxDeltaMg,
                       static_cast<int16_t>(mMinuteSum[0] / k),
                       static_cast<int16_t>(mMinuteSum[1] / k),
                       static_cast<int16_t>(mMinuteSum[2] / k));
        mPolicy.onIdleMinute(mMinuteMaxDeltaMg, s.tMs);
        mMinuteSamples = 0;
    }
}

// --------------------------------------------------------------------- mode

void Service::applyTransition(const Transition& t, uint32_t nowMs)
{
    LOG_INFO("mode -> %u (reason %u)\n", unsigned(t.to), unsigned(t.reason));
    // Recorded at the end of the old chunk and again at the start of the new
    // one, so each file says on its own which mode it was written in.
    mWriter.mode(nowMs, static_cast<uint8_t>(t.to), static_cast<uint8_t>(t.reason));
    // A mode change always starts a fresh chunk, so the idle lead-in before a
    // recording is fetchable at once rather than when its 6-hour chunk closes.
    closeChunk();
    openChunk(nowMs);
    mWriter.mode(nowMs, static_cast<uint8_t>(t.to), static_cast<uint8_t>(t.reason));
    if (t.to == Mode::RECORDING) {
        mRecordingSinceUtc = std::time(nullptr);
        connectRecording();
    } else {
        connectIdle();
    }
    refreshGlance();
}

// ------------------------------------------------------------------- glance

void Service::onGlanceStart()
{
    mGlanceVisible = true;
    if (!mGlanceBuilt) {
        // Unlike the SDK's example glances, a refused config is not a reason
        // to exit: the tile is optional, the recording is the point.
        auto gc = SDK::make_msg<SDK::Message::RequestGlanceConfig>(mKernel);
        if (!gc || !gc.send(100) || !gc.ok() || gc->maxControls < 2) {
            LOG_WARNING("glance config refused; no tile\n");
            return;
        }
        mGlanceUI.setWidth(gc->width);
        mGlanceUI.setHeight(gc->height);
        mGlanceTitle = mGlanceUI.createText();
        mGlanceTitle.pos({kTitleX, kTitleY}, {kTitleW, kTitleH})
            .font(GlanceFont_t::GLANCE_FONT_POPPINS_SEMIBOLD_20)
            .color(GlanceColor_t::GLANCE_COLOR_TEAL)
            .setText("Sleep Log")
            .alignment(GlanceAlignH_t::GLANCE_ALIGN_H_CENTER);
        mGlanceValue = mGlanceUI.createText();
        mGlanceValue.pos({kValueX, kValueY}, {kValueW, kValueH})
            .font(GlanceFont_t::GLANCE_FONT_POPPINS_MEDIUM_18)
            .color(GlanceColor_t::GLANCE_COLOR_WHITE)
            .setText("---")
            .alignment(GlanceAlignH_t::GLANCE_ALIGN_H_CENTER);
        mGlanceBuilt = true;
    }
    refreshGlance();
    pushGlance();
}

void Service::refreshGlance()
{
    if (!mGlanceBuilt) return;
    if (mPolicy.mode() == Mode::RECORDING) {
        std::tm local {};
        localtime_r(&mRecordingSinceUtc, &local);
        mGlanceValue.print("Recording since %02d:%02d", local.tm_hour, local.tm_min);
    } else if (mPolicy.stillMinutes() > 0) {
        mGlanceValue.print("Idle, still %u/%u min",
                           unsigned(mPolicy.stillMinutes()),
                           unsigned(mPolicy.config().stillMinutesToStart));
    } else {
        mGlanceValue.setText("Idle");
    }
}

void Service::pushGlance()
{
    if (!mGlanceBuilt || !mGlanceVisible || !mGlanceUI.isInvalid()) return;
    if (auto upd = SDK::make_msg<SDK::Message::RequestGlanceUpdate>(mKernel)) {
        upd->name           = APP_NAME;
        upd->controls       = mGlanceUI.data();
        upd->controlsNumber = static_cast<uint32_t>(mGlanceUI.size());
        upd.send(100);
    }
    mGlanceUI.setValid();
}

// -------------------------------------------------------------------- files

bool Service::openChunk(uint32_t nowMs)
{
    const std::time_t utc = std::time(nullptr);
    std::tm local {};
    localtime_r(&utc, &local);

    char dir[48];
    std::snprintf(dir, sizeof(dir), "%s/%04d%02d%02d", kRoot,
                  local.tm_year + 1900, local.tm_mon + 1, local.tm_mday);
    mKernel.fs.mkdir(kRoot);
    if (!mKernel.fs.mkdir(dir)) {
        LOG_ERROR("mkdir %s failed\n", dir);
        return false;
    }

    // HHMMSS, with -1, -2... on the rare collision (two chunks in one second).
    char stem[sizeof(mChunkPath)];
    for (int bump = 0; bump < 10; ++bump) {
        if (bump == 0) {
            std::snprintf(stem, sizeof(stem), "%s/%02d%02d%02d", dir,
                          local.tm_hour, local.tm_min, local.tm_sec);
        } else {
            std::snprintf(stem, sizeof(stem), "%s/%02d%02d%02d-%d", dir,
                          local.tm_hour, local.tm_min, local.tm_sec, bump);
        }
        char bin[sizeof(mChunkPath) + 8];
        std::snprintf(mChunkPath, sizeof(mChunkPath), "%s.part", stem);
        std::snprintf(bin, sizeof(bin), "%s.bin", stem);
        if (!mKernel.fs.exist(mChunkPath) && !mKernel.fs.exist(bin)) break;
    }

    mSink.file = mKernel.fs.file(mChunkPath);
    if (!mSink.file || !mSink.file->open(true, true)) {
        LOG_ERROR("open %s failed\n", mChunkPath);
        mSink.file.reset();
        return false;
    }
    mChunkOpen = true;
    mChunkOpenedMs = nowMs;
    mLastFlushMs = nowMs;
    mWriter.reset();
    mWriter.begin(nowMs, static_cast<uint32_t>(utc), utcOffsetSeconds(utc));
    pruneOldDays();
    return true;
}

void Service::closeChunk()
{
    if (!mChunkOpen) return;
    mWriter.flush();
    mSink.file->flush();
    mSink.file->close();
    mSink.file.reset();
    mChunkOpen = false;

    // Publish: Helf only fetches *.bin, so a chunk is never read half-written.
    char bin[sizeof(mChunkPath)];
    std::snprintf(bin, sizeof(bin), "%.*s.bin", int(std::strlen(mChunkPath) - 5), mChunkPath);
    if (!mKernel.fs.rename(mChunkPath, bin)) {
        LOG_ERROR("rename %s failed\n", mChunkPath);
    }
}

void Service::rotateIfDue(uint32_t nowMs)
{
    if (!mChunkOpen) {
        openChunk(nowMs);
        return;
    }
    const uint32_t limit = mPolicy.mode() == Mode::RECORDING ? kRecChunkMs : kIdleChunkMs;
    if (nowMs - mChunkOpenedMs >= limit) {
        closeChunk();
        openChunk(nowMs);
    } else if (nowMs - mLastFlushMs >= kFlushMs) {
        // Persist as we go: a reboot gives no warning (service-lifecycle §7).
        mWriter.flush();
        mSink.file->flush();
        mLastFlushMs = nowMs;
    }
}

void Service::recoverPartials()
{
    // A .part left by a reboot or power loss is complete up to its last flush;
    // the decoder drops a torn final record. Publish it.
    auto root = mKernel.fs.dir(kRoot);
    if (!root || !root->open()) return;
    SDK::Interface::IFileSystem::ObjectInfo day {};
    while (root->readNext(day)) {
        if (!day.isDir) continue;
        char dayPath[48];
        std::snprintf(dayPath, sizeof(dayPath), "%s/%s", kRoot, day.name);
        auto d = mKernel.fs.dir(dayPath);
        if (!d || !d->open()) continue;
        SDK::Interface::IFileSystem::ObjectInfo f {};
        while (d->readNext(f)) {
            const size_t len = std::strlen(f.name);
            if (f.isDir || len < 6 || std::strcmp(f.name + len - 5, ".part") != 0) continue;
            char from[128], to[128];
            std::snprintf(from, sizeof(from), "%s/%s", dayPath, f.name);
            std::snprintf(to, sizeof(to), "%s/%.*s.bin", dayPath, int(len - 5), f.name);
            mKernel.fs.rename(from, to);
        }
        d->close();
    }
    root->close();
}

void Service::pruneOldDays()
{
    // Keep the newest kKeepDays day directories. Helf polls every 15 minutes,
    // so two weeks is a long margin; without a limit the watch fills up.
    struct Day { char name[9]; };
    Day days[32] {};
    uint32_t count = 0;
    auto root = mKernel.fs.dir(kRoot);
    if (!root || !root->open()) return;
    SDK::Interface::IFileSystem::ObjectInfo e {};
    while (root->readNext(e) && count < 32) {
        if (e.isDir && std::strlen(e.name) == 8) std::snprintf(days[count++].name, 9, "%s", e.name);
    }
    root->close();
    if (count <= kKeepDays) return;

    // YYYYMMDD sorts as text in date order.
    std::sort(days, days + count,
              [](const Day& a, const Day& b) { return std::strcmp(a.name, b.name) < 0; });
    for (uint32_t i = 0; i + kKeepDays < count; ++i) {
        char dayPath[48];
        std::snprintf(dayPath, sizeof(dayPath), "%s/%s", kRoot, days[i].name);
        auto d = mKernel.fs.dir(dayPath);
        if (d && d->open()) {
            SDK::Interface::IFileSystem::ObjectInfo f {};
            while (d->readNext(f)) {
                char p[128];
                std::snprintf(p, sizeof(p), "%s/%s", dayPath, f.name);
                mKernel.fs.remove(p);
            }
            d->close();
        }
        mKernel.fs.remove(dayPath);
    }
}

// --------------------------------------------------------------------- loop

void Service::run()
{
    LOG_INFO("Started\n");
    const uint32_t start = mKernel.sys.getTimeMs();

    recoverPartials();
    openChunk(start);
    mWriter.mode(start, static_cast<uint8_t>(Mode::IDLE), static_cast<uint8_t>(Reason::STARTUP));

    mTouch.connect();
    mSteps.connect();
    mCharging.connect();
    mMotion.connect();
    connectIdle();

    while (true) {
        SDK::MessageBase* msg = nullptr;
        // Bounded wait: nothing paces a resident service (service-lifecycle
        // §4.2), and rotation and the policy's timers must run regardless.
        if (mKernel.comm.getMessage(msg, kLoopWaitMs)) {
            switch (msg->getType()) {
                case SDK::MessageType::COMMAND_APP_STOP: {
                    const uint32_t now = mKernel.sys.getTimeMs();
                    mWriter.mode(now, static_cast<uint8_t>(mPolicy.mode()),
                                 static_cast<uint8_t>(Reason::SHUTDOWN));
                    closeChunk();
                    mKernel.comm.releaseMessage(msg);
                    return;
                }
                case SDK::MessageType::EVENT_SENSOR_LAYER_DATA: {
                    auto* event = static_cast<SDK::Message::Sensor::EventData*>(msg);
                    SDK::Sensor::DataBatch batch(event->data, event->count, event->stride);
                    handleSensors(event->handle, batch);
                    break;
                }
                case SDK::MessageType::EVENT_GLANCE_START:
                    onGlanceStart();
                    break;
                case SDK::MessageType::EVENT_GLANCE_TICK:
                    refreshGlance();
                    pushGlance();
                    break;
                case SDK::MessageType::EVENT_GLANCE_STOP:
                    // The tile went off screen. The service is resident for
                    // the recording, so this is not the exit GlanceSteps takes.
                    mGlanceVisible = false;
                    break;
                default:
                    // No GUI, no custom messages: anything else is ignored.
                    break;
            }
            mKernel.comm.releaseMessage(msg);
        }

        const uint32_t now = mKernel.sys.getTimeMs();
        Transition t {};
        if (mPolicy.evaluate(now, t)) applyTransition(t, now);
        rotateIfDue(now);
    }
}
