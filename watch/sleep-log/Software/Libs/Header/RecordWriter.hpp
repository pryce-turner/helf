/**
 * Encodes SleepLog records into a RAM buffer and hands full buffers to a sink.
 *
 * No SDK dependency, so it is tested on the host (`Tests/`). The service
 * adapts the sink onto an `SDK::Interface::IFile`.
 */

#pragma once

#include <cstddef>
#include <cstdint>

#include "Format.hpp"

namespace SleepLog {

class ByteSink {
public:
    virtual bool write(const uint8_t* data, size_t size) = 0;

protected:
    ~ByteSink() = default;
};

struct AccelSample {
    uint32_t tMs;
    int16_t  x, y, z;  ///< milli-g
};

class RecordWriter {
public:
    explicit RecordWriter(ByteSink& sink) : mSink(sink) {}

    /// Starts a file: header, then CLOCK.
    bool begin(uint32_t bootMs, uint32_t unixS, int32_t utcOffsetS);

    bool clock(uint32_t bootMs, uint32_t unixS, int32_t utcOffsetS);
    /// Splits into blocks of ≤ 255 samples, or wherever a gap exceeds 255 ms.
    bool accel(const AccelSample* samples, size_t count);
    bool hr(uint32_t tMs, float bpm, float trust);
    bool touch(uint32_t tMs, bool worn);
    bool charging(uint32_t tMs, bool connected, bool isCharging);
    bool steps(uint32_t tMs, uint32_t count);
    bool mode(uint32_t tMs, uint8_t mode, uint8_t reason);
    bool minute(uint32_t tMs, uint16_t samples, uint16_t movementMg,
                int16_t x, int16_t y, int16_t z);
    bool motion(uint32_t tMs, uint8_t state);

    /// Pushes whatever is buffered to the sink.
    bool flush();

    /// Forgets buffered bytes and counters, for a new file on the same sink.
    void reset() { mUsed = 0; mFlushed = 0; }

    /// Bytes handed to the sink plus bytes still buffered.
    size_t bytesWritten() const { return mFlushed + mUsed; }

    static constexpr size_t kBufferSize = 4096;

private:
    bool reserve(size_t n);
    void u8(uint8_t v);
    void u16(uint16_t v);
    void u32(uint32_t v);
    void i16(int16_t v) { u16(static_cast<uint16_t>(v)); }
    void i32(int32_t v) { u32(static_cast<uint32_t>(v)); }
    void f32(float v);

    ByteSink& mSink;
    uint8_t   mBuf[kBufferSize] {};
    size_t    mUsed    = 0;
    size_t    mFlushed = 0;
};

} // namespace SleepLog
