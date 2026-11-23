// Host tests for the SDK-free parts of SleepLog: the mode policy and the
// record encoder. No framework: `make -C watch/sleep-log/Tests` builds and
// runs them with the host compiler.
//
// `--fixture <path>` also writes a chunk file covering every record type.
// Helf's decoder test (backend/tests/test_sleep_log.py) reads the committed
// copy, so the C++ encoder and the Python decoder are checked against the
// same bytes.

#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "RecordWriter.hpp"
#include "SleepPolicy.hpp"

using namespace SleepLog;

static int gFailures = 0;
static int gChecks = 0;

#define CHECK(cond)                                                                   \
    do {                                                                              \
        ++gChecks;                                                                    \
        if (!(cond)) {                                                                \
            ++gFailures;                                                              \
            std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);               \
        }                                                                             \
    } while (0)

static constexpr uint32_t kMin = 60u * 1000u;

// ------------------------------------------------------------------- policy

static void stillFor(SleepPolicy& p, uint32_t& now, int minutes, uint16_t mg = 10)
{
    for (int i = 0; i < minutes; ++i) {
        now += kMin;
        p.onIdleMinute(mg, now);
    }
}

static void test_starts_after_twenty_still_minutes_while_worn()
{
    SleepPolicy p;
    uint32_t now = 1000;
    Transition t {};
    p.onTouch(true, now);
    stillFor(p, now, 19);
    CHECK(!p.evaluate(now, t));
    stillFor(p, now, 1);
    CHECK(p.evaluate(now, t));
    CHECK(t.to == Mode::RECORDING && t.reason == Reason::STILL);
}

static void test_nightstand_never_starts()
{
    SleepPolicy p;
    uint32_t now = 1000;
    Transition t {};
    p.onTouch(false, now);
    stillFor(p, now, 120);
    CHECK(!p.evaluate(now, t));
}

static void test_charger_blocks_start()
{
    SleepPolicy p;
    uint32_t now = 1000;
    Transition t {};
    p.onTouch(true, now);
    p.onCharging(true, now);
    stillFor(p, now, 60);
    CHECK(!p.evaluate(now, t));
}

static void test_one_restless_minute_resets_the_count()
{
    SleepPolicy p;
    uint32_t now = 1000;
    Transition t {};
    p.onTouch(true, now);
    stillFor(p, now, 15);
    stillFor(p, now, 1, 400);
    stillFor(p, now, 15);
    CHECK(!p.evaluate(now, t));
    stillFor(p, now, 5);
    CHECK(p.evaluate(now, t));
}

static SleepPolicy recording(uint32_t& now)
{
    SleepPolicy p;
    Transition t {};
    p.onTouch(true, now);
    stillFor(p, now, 20);
    p.evaluate(now, t);
    return p;
}

static void test_rolling_over_does_not_stop()
{
    uint32_t now = 1000;
    SleepPolicy p = recording(now);
    Transition t {};
    // Ignored while recording: tossing in bed is part of sleep.
    p.onIdleMinute(2000, now);
    p.onSteps(5000, now);
    now += 3 * kMin;
    p.onSteps(5012, now);  // a few steps' worth of arm movement
    CHECK(!p.evaluate(now, t));
    CHECK(p.mode() == Mode::RECORDING);
}

static void test_walking_stops()
{
    uint32_t now = 1000;
    SleepPolicy p = recording(now);
    Transition t {};
    p.onSteps(5000, now);
    for (int i = 1; i <= 5; ++i) {
        now += kMin;
        p.onSteps(5000 + i * 25, now);
    }
    CHECK(p.evaluate(now, t));
    CHECK(t.to == Mode::IDLE && t.reason == Reason::WALKING);
}

static void test_slow_steps_across_hours_do_not_stop()
{
    uint32_t now = 1000;
    SleepPolicy p = recording(now);
    Transition t {};
    // 30 steps every 20 min: 180 over two hours, never 100 within 10 min.
    for (int i = 0; i <= 6; ++i) {
        p.onSteps(5000 + i * 30, now);
        CHECK(!p.evaluate(now, t));
        now += 20 * kMin;
    }
}

static void test_steps_from_before_the_recording_do_not_count()
{
    // A short start threshold puts the walk to bed inside the 10-minute step
    // window when recording begins, which is the case the guard exists for.
    PolicyConfig cfg;
    cfg.stillMinutesToStart = 2;
    SleepPolicy p(cfg);
    uint32_t now = 1000;
    Transition t {};
    p.onTouch(true, now);
    p.onSteps(1000, now);
    now += kMin;
    p.onSteps(1150, now);  // walked to bed: 150 steps
    stillFor(p, now, 2);
    CHECK(p.evaluate(now, t));
    CHECK(t.to == Mode::RECORDING);
    now += kMin;
    p.onSteps(1150, now);
    CHECK(!p.evaluate(now, t));
    CHECK(p.mode() == Mode::RECORDING);
}

static void test_unworn_stops_after_five_minutes()
{
    uint32_t now = 1000;
    SleepPolicy p = recording(now);
    Transition t {};
    p.onTouch(false, now);
    now += 4 * kMin;
    CHECK(!p.evaluate(now, t));
    now += kMin;
    CHECK(p.evaluate(now, t));
    CHECK(t.reason == Reason::UNWORN);
}

static void test_brief_loss_of_contact_does_not_stop()
{
    uint32_t now = 1000;
    SleepPolicy p = recording(now);
    Transition t {};
    p.onTouch(false, now);
    now += 2 * kMin;
    p.onTouch(true, now);
    now += 10 * kMin;
    CHECK(!p.evaluate(now, t));
}

static void test_charger_stops_and_cap_stops()
{
    uint32_t now = 1000;
    SleepPolicy p = recording(now);
    Transition t {};
    p.onCharging(true, now);
    CHECK(p.evaluate(now, t) && t.reason == Reason::CHARGING);

    uint32_t now2 = 5000;
    SleepPolicy q = recording(now2);
    now2 += 14u * 60u * kMin;
    CHECK(q.evaluate(now2, t) && t.reason == Reason::MAX_DURATION);
}

static void test_clock_wrap_is_harmless()
{
    uint32_t now = 0xFFFFFFFFu - 10u * kMin;  // ten minutes before the u32 wraps
    SleepPolicy p;
    Transition t {};
    p.onTouch(true, now);
    stillFor(p, now, 20);  // crosses the wrap
    CHECK(p.evaluate(now, t));
    now += 13u * 60u * kMin;
    CHECK(!p.evaluate(now, t));
    now += 60u * kMin;
    CHECK(p.evaluate(now, t) && t.reason == Reason::MAX_DURATION);
}

// ------------------------------------------------------------------- writer

struct MemorySink : ByteSink {
    std::vector<uint8_t> bytes;
    bool fail = false;
    bool write(const uint8_t* data, size_t size) override
    {
        if (fail) return false;
        bytes.insert(bytes.end(), data, data + size);
        return true;
    }
};

static uint32_t rd32(const std::vector<uint8_t>& b, size_t at)
{
    return b[at] | (b[at + 1] << 8) | (b[at + 2] << 16) | (uint32_t(b[at + 3]) << 24);
}

static void test_header_and_clock()
{
    MemorySink sink;
    RecordWriter w(sink);
    CHECK(w.begin(1234, 1763900000, -28800));
    CHECK(w.flush());
    CHECK(sink.bytes.size() == 8 + 13);
    CHECK(std::memcmp(sink.bytes.data(), "USL1", 4) == 0);
    CHECK(sink.bytes[4] == 1 && sink.bytes[5] == 0);
    CHECK(sink.bytes[8] == Format::CLOCK);
    CHECK(rd32(sink.bytes, 9) == 1234);
    CHECK(rd32(sink.bytes, 13) == 1763900000u);
    CHECK(int32_t(rd32(sink.bytes, 17)) == -28800);
}

static void test_accel_blocks_split_at_255_and_at_gaps()
{
    MemorySink sink;
    RecordWriter w(sink);
    std::vector<AccelSample> s;
    for (int i = 0; i < 300; ++i) s.push_back({uint32_t(1000 + i * 20), int16_t(i), 0, 1000});
    s.push_back({s.back().tMs + 1000, 1, 2, 3});  // a gap a u8 cannot carry
    CHECK(w.accel(s.data(), s.size()));
    CHECK(w.flush());
    // Blocks: 255, 45, 1.
    size_t at = 0, blocks = 0, samples = 0;
    while (at < sink.bytes.size()) {
        CHECK(sink.bytes[at] == Format::ACCEL_BLOCK);
        const uint8_t n = sink.bytes[at + 1];
        samples += n;
        ++blocks;
        at += 6 + size_t(n) * 7;
    }
    CHECK(at == sink.bytes.size());
    CHECK(blocks == 3);
    CHECK(samples == 301);
}

static void test_buffer_spills_to_the_sink_without_loss()
{
    MemorySink sink;
    RecordWriter w(sink);
    for (int i = 0; i < 1000; ++i) w.hr(uint32_t(i * 1000), 60.0f, 1.0f);
    CHECK(w.bytesWritten() == 13000);
    CHECK(w.flush());
    CHECK(sink.bytes.size() == 13000);
}

static void test_a_failing_sink_is_reported()
{
    MemorySink sink;
    sink.fail = true;
    RecordWriter w(sink);
    bool ok = true;
    for (int i = 0; i < 1000 && ok; ++i) ok = w.hr(uint32_t(i), 60.0f, 1.0f);
    CHECK(!ok);
}

// ------------------------------------------------------------------ fixture

static bool writeFixture(const char* path)
{
    MemorySink sink;
    RecordWriter w(sink);
    w.begin(5000, 1763938800, -28800);  // 2026-11-23 23:00 UTC, PST
    w.mode(5000, 0, uint8_t(Reason::STARTUP));
    w.touch(5100, true);
    w.charging(5200, false, false);
    w.steps(5300, 4321);
    w.motion(5400, 0);
    w.minute(65000, 60, 12, -20, 15, 990);
    w.mode(70000, 1, uint8_t(Reason::STILL));
    std::vector<AccelSample> s;
    for (int i = 0; i < 100; ++i) {
        s.push_back({uint32_t(70000 + i * 20), int16_t(i - 50), int16_t(-i), int16_t(1000 + i % 3)});
    }
    w.accel(s.data(), s.size());
    w.hr(71000, 58.5f, 0.75f);
    w.hr(72000, 57.25f, 1.0f);
    w.mode(80000, 0, uint8_t(Reason::WALKING));
    w.flush();
    // A torn final record, as a power loss leaves: HR tag plus two bytes.
    sink.bytes.push_back(Format::HR);
    sink.bytes.push_back(0x10);
    sink.bytes.push_back(0x27);

    FILE* f = std::fopen(path, "wb");
    if (!f) return false;
    const bool ok = std::fwrite(sink.bytes.data(), 1, sink.bytes.size(), f) == sink.bytes.size();
    std::fclose(f);
    return ok;
}

int main(int argc, char** argv)
{
    test_starts_after_twenty_still_minutes_while_worn();
    test_nightstand_never_starts();
    test_charger_blocks_start();
    test_one_restless_minute_resets_the_count();
    test_rolling_over_does_not_stop();
    test_walking_stops();
    test_slow_steps_across_hours_do_not_stop();
    test_steps_from_before_the_recording_do_not_count();
    test_unworn_stops_after_five_minutes();
    test_brief_loss_of_contact_does_not_stop();
    test_charger_stops_and_cap_stops();
    test_clock_wrap_is_harmless();
    test_header_and_clock();
    test_accel_blocks_split_at_255_and_at_gaps();
    test_buffer_spills_to_the_sink_without_loss();
    test_a_failing_sink_is_reported();

    if (argc == 3 && std::strcmp(argv[1], "--fixture") == 0) {
        if (!writeFixture(argv[2])) {
            std::printf("could not write fixture %s\n", argv[2]);
            return 2;
        }
    }

    std::printf("%d checks, %d failed\n", gChecks, gFailures);
    return gFailures ? 1 : 0;
}
