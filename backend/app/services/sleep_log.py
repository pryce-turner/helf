"""Decoder for SleepLog chunk files from the UNA Watch (plan 0024 §4).

The format is defined in ``watch/sleep-log/Software/Libs/Header/Format.hpp``;
change both together and regenerate the fixture
(``make -C watch/sleep-log/Tests fixture``), which ``test_sleep_log.py`` reads.

Pure: bytes in, records out. Nothing here touches the database. Feature
extraction and scoring (the Walch method) build on this in a later step.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b"USL1"
VERSION = 1
HEADER = struct.Struct("<4sHH")

MODE_NAMES = {0: "idle", 1: "recording"}
REASON_NAMES = {
    0: "none",
    1: "still",
    2: "walking",
    3: "unworn",
    4: "charging",
    5: "max_duration",
    6: "startup",
    7: "shutdown",
}


class SleepLogError(ValueError):
    """Not a SleepLog file, or a version this decoder does not know."""


@dataclass
class Chunk:
    version: int
    # (boot_ms, unix_s, utc_offset_s); the first is always the file's own.
    clocks: list[tuple[int, int, int]] = field(default_factory=list)
    # (t_ms, x_mg, y_mg, z_mg)
    accel: list[tuple[int, int, int, int]] = field(default_factory=list)
    # (t_ms, bpm, trust)
    hr: list[tuple[int, float, float]] = field(default_factory=list)
    touch: list[tuple[int, bool]] = field(default_factory=list)
    charging: list[tuple[int, bool, bool]] = field(default_factory=list)
    steps: list[tuple[int, int]] = field(default_factory=list)
    # (t_ms, mode, reason) as names
    modes: list[tuple[int, str, str]] = field(default_factory=list)
    # (t_ms, samples, movement_mg, x_mg, y_mg, z_mg)
    minutes: list[tuple[int, int, int, int, int, int]] = field(default_factory=list)
    motion: list[tuple[int, int]] = field(default_factory=list)
    # Bytes left over after the last whole record: a power loss mid-write.
    torn_bytes: int = 0

    def to_unix(self, t_ms: int) -> float:
        """Seconds since the epoch for a boot-relative timestamp.

        Uses the last CLOCK at or before ``t_ms``. Unsigned 32-bit
        subtraction, so a millisecond clock that wrapped still maps.
        """
        boot_ms, unix_s, _ = self.clocks[0]
        for c in self.clocks:
            if ((t_ms - c[0]) & 0xFFFFFFFF) < 0x80000000:
                boot_ms, unix_s, _ = c
        delta = (t_ms - boot_ms) & 0xFFFFFFFF
        if delta >= 0x80000000:
            delta -= 0x100000000
        return unix_s + delta / 1000.0


# Fixed-size records: tag -> payload struct (after the tag byte).
_FIXED = {
    0x01: struct.Struct("<IIi"),  # CLOCK
    0x03: struct.Struct("<Iff"),  # HR
    0x04: struct.Struct("<IB"),  # TOUCH
    0x05: struct.Struct("<IBB"),  # CHARGING
    0x06: struct.Struct("<II"),  # STEPS
    0x07: struct.Struct("<IBB"),  # MODE
    0x08: struct.Struct("<IHHhhh"),  # MINUTE
    0x09: struct.Struct("<IB"),  # MOTION
}
_ACCEL_HEAD = struct.Struct("<BI")
_ACCEL_SAMPLE = struct.Struct("<Bhhh")


def decode(data: bytes) -> Chunk:
    if len(data) < HEADER.size:
        raise SleepLogError("too short for a SleepLog header")
    magic, version, _ = HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise SleepLogError(f"bad magic {magic!r}")
    if version != VERSION:
        raise SleepLogError(f"unknown SleepLog version {version}")

    chunk = Chunk(version=version)
    at = HEADER.size
    end = len(data)
    while at < end:
        tag = data[at]
        if tag == 0x02:
            if at + 1 + _ACCEL_HEAD.size > end:
                break
            n, t = _ACCEL_HEAD.unpack_from(data, at + 1)
            size = 1 + _ACCEL_HEAD.size + n * _ACCEL_SAMPLE.size
            if at + size > end:
                break
            pos = at + 1 + _ACCEL_HEAD.size
            for _ in range(n):
                dt, x, y, z = _ACCEL_SAMPLE.unpack_from(data, pos)
                t = (t + dt) & 0xFFFFFFFF
                chunk.accel.append((t, x, y, z))
                pos += _ACCEL_SAMPLE.size
            at += size
            continue

        fmt = _FIXED.get(tag)
        if fmt is None:
            raise SleepLogError(f"unknown record tag 0x{tag:02x} at byte {at}")
        if at + 1 + fmt.size > end:
            break
        v = fmt.unpack_from(data, at + 1)
        at += 1 + fmt.size

        if tag == 0x01:
            chunk.clocks.append(v)
        elif tag == 0x03:
            chunk.hr.append(v)
        elif tag == 0x04:
            chunk.touch.append((v[0], bool(v[1])))
        elif tag == 0x05:
            chunk.charging.append((v[0], bool(v[1]), bool(v[2])))
        elif tag == 0x06:
            chunk.steps.append(v)
        elif tag == 0x07:
            chunk.modes.append(
                (v[0], MODE_NAMES.get(v[1], str(v[1])), REASON_NAMES.get(v[2], str(v[2])))
            )
        elif tag == 0x08:
            chunk.minutes.append(v)
        elif tag == 0x09:
            chunk.motion.append(v)

    chunk.torn_bytes = end - at
    if not chunk.clocks:
        raise SleepLogError("no CLOCK record: cannot place the chunk in time")
    return chunk
