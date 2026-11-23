/**
 * SleepLog file format, version 1. The contract with Helf's decoder
 * (`backend/app/services/sleep_log.py`, plan 0024 §4) — change both together.
 *
 * A chunk file is an 8-byte header followed by self-delimiting records, all
 * little-endian. The first record of every file is CLOCK, so each file can be
 * placed on the wall clock on its own. A torn last record (power loss
 * mid-write) is expected and is dropped by the decoder.
 *
 * Header:  'U' 'S' 'L' '1'  version:u16  reserved:u16
 *
 * | Tag  | Record        | Payload after the tag byte                                   |
 * |------|---------------|--------------------------------------------------------------|
 * | 0x01 | CLOCK         | boot_ms:u32  unix_s:u32  utc_offset_s:i32                    |
 * | 0x02 | ACCEL_BLOCK   | n:u8  t0_ms:u32  n × (dt_ms:u8  x:i16  y:i16  z:i16) milli-g |
 * | 0x03 | HR            | t_ms:u32  bpm:f32  trust:f32                                 |
 * | 0x04 | TOUCH         | t_ms:u32  worn:u8                                            |
 * | 0x05 | CHARGING      | t_ms:u32  connected:u8  charging:u8                          |
 * | 0x06 | STEPS         | t_ms:u32  count:u32 (since boot)                             |
 * | 0x07 | MODE          | t_ms:u32  mode:u8  reason:u8                                 |
 * | 0x08 | MINUTE        | t_ms:u32  samples:u16  movement_mg:u16  x:i16 y:i16 z:i16    |
 * | 0x09 | MOTION        | t_ms:u32  state:u8                                           |
 *
 * Times are milliseconds since boot (the sensor timestamps and
 * `sys.getTimeMs()`); CLOCK pairs one with Unix time. In ACCEL_BLOCK the first
 * sample's dt is 0 and each later dt is from the previous sample.
 */

#pragma once

#include <cstdint>

namespace SleepLog::Format {

constexpr uint8_t  kMagic[4] = {'U', 'S', 'L', '1'};
constexpr uint16_t kVersion  = 1;
constexpr uint32_t kHeaderSize = 8;

enum Tag : uint8_t {
    CLOCK       = 0x01,
    ACCEL_BLOCK = 0x02,
    HR          = 0x03,
    TOUCH       = 0x04,
    CHARGING    = 0x05,
    STEPS       = 0x06,
    MODE        = 0x07,
    MINUTE      = 0x08,
    MOTION      = 0x09,
};

/// Samples per ACCEL_BLOCK at most (n is a u8).
constexpr uint8_t kMaxBlockSamples = 255;

} // namespace SleepLog::Format
