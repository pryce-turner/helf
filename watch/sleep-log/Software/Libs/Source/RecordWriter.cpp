#include "RecordWriter.hpp"

#include <cstring>

namespace SleepLog {

bool RecordWriter::reserve(size_t n)
{
    if (mUsed + n <= kBufferSize) return true;
    return flush() && n <= kBufferSize;
}

bool RecordWriter::flush()
{
    if (mUsed == 0) return true;
    if (!mSink.write(mBuf, mUsed)) return false;
    mFlushed += mUsed;
    mUsed = 0;
    return true;
}

void RecordWriter::u8(uint8_t v) { mBuf[mUsed++] = v; }

void RecordWriter::u16(uint16_t v)
{
    u8(static_cast<uint8_t>(v));
    u8(static_cast<uint8_t>(v >> 8));
}

void RecordWriter::u32(uint32_t v)
{
    u16(static_cast<uint16_t>(v));
    u16(static_cast<uint16_t>(v >> 16));
}

void RecordWriter::f32(float v)
{
    uint32_t bits;
    static_assert(sizeof(bits) == sizeof(v), "IEEE-754 single expected");
    std::memcpy(&bits, &v, sizeof(bits));
    u32(bits);
}

bool RecordWriter::begin(uint32_t bootMs, uint32_t unixS, int32_t utcOffsetS)
{
    if (!reserve(Format::kHeaderSize)) return false;
    for (uint8_t b : Format::kMagic) u8(b);
    u16(Format::kVersion);
    u16(0);
    return clock(bootMs, unixS, utcOffsetS);
}

bool RecordWriter::clock(uint32_t bootMs, uint32_t unixS, int32_t utcOffsetS)
{
    if (!reserve(13)) return false;
    u8(Format::CLOCK);
    u32(bootMs);
    u32(unixS);
    i32(utcOffsetS);
    return true;
}

bool RecordWriter::accel(const AccelSample* samples, size_t count)
{
    size_t i = 0;
    while (i < count) {
        // Size the block first: it ends at 255 samples or at a gap a u8
        // millisecond delta cannot carry.
        size_t n = 1;
        while (i + n < count && n < Format::kMaxBlockSamples) {
            const uint32_t dt = samples[i + n].tMs - samples[i + n - 1].tMs;
            if (dt > 0xFF) break;
            ++n;
        }
        if (!reserve(6 + n * 7)) return false;
        u8(Format::ACCEL_BLOCK);
        u8(static_cast<uint8_t>(n));
        u32(samples[i].tMs);
        for (size_t k = 0; k < n; ++k) {
            const AccelSample& s = samples[i + k];
            u8(k == 0 ? 0 : static_cast<uint8_t>(s.tMs - samples[i + k - 1].tMs));
            i16(s.x);
            i16(s.y);
            i16(s.z);
        }
        i += n;
    }
    return true;
}

bool RecordWriter::hr(uint32_t tMs, float bpm, float trust)
{
    if (!reserve(13)) return false;
    u8(Format::HR);
    u32(tMs);
    f32(bpm);
    f32(trust);
    return true;
}

bool RecordWriter::touch(uint32_t tMs, bool worn)
{
    if (!reserve(6)) return false;
    u8(Format::TOUCH);
    u32(tMs);
    u8(worn ? 1 : 0);
    return true;
}

bool RecordWriter::charging(uint32_t tMs, bool connected, bool isCharging)
{
    if (!reserve(7)) return false;
    u8(Format::CHARGING);
    u32(tMs);
    u8(connected ? 1 : 0);
    u8(isCharging ? 1 : 0);
    return true;
}

bool RecordWriter::steps(uint32_t tMs, uint32_t count)
{
    if (!reserve(9)) return false;
    u8(Format::STEPS);
    u32(tMs);
    u32(count);
    return true;
}

bool RecordWriter::mode(uint32_t tMs, uint8_t mode, uint8_t reason)
{
    if (!reserve(7)) return false;
    u8(Format::MODE);
    u32(tMs);
    u8(mode);
    u8(reason);
    return true;
}

bool RecordWriter::minute(uint32_t tMs, uint16_t samples, uint16_t movementMg,
                          int16_t x, int16_t y, int16_t z)
{
    if (!reserve(15)) return false;
    u8(Format::MINUTE);
    u32(tMs);
    u16(samples);
    u16(movementMg);
    i16(x);
    i16(y);
    i16(z);
    return true;
}

bool RecordWriter::motion(uint32_t tMs, uint8_t state)
{
    if (!reserve(6)) return false;
    u8(Format::MOTION);
    u32(tMs);
    u8(state);
    return true;
}

} // namespace SleepLog
