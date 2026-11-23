"""SleepLog decoder against bytes the watch app's own encoder wrote.

``fixtures/sleep_log_v1.bin`` is produced by ``make -C watch/sleep-log/Tests
fixture`` from the C++ RecordWriter, so this test is the check that the two
sides of the format agree. The values asserted are the ones ``writeFixture``
in ``watch/sleep-log/Tests/test_main.cpp`` writes.
"""

from pathlib import Path

import pytest

from app.services.sleep_log import SleepLogError, decode

FIXTURE = Path(__file__).parent / "fixtures" / "sleep_log_v1.bin"


@pytest.fixture(scope="module")
def chunk():
    return decode(FIXTURE.read_bytes())


def test_clock_places_the_chunk_on_the_wall_clock(chunk):
    assert chunk.clocks == [(5000, 1763938800, -28800)]
    assert chunk.to_unix(5000) == 1763938800
    assert chunk.to_unix(70000) == 1763938800 + 65


def test_every_record_type_decodes(chunk):
    assert chunk.touch == [(5100, True)]
    assert chunk.charging == [(5200, False, False)]
    assert chunk.steps == [(5300, 4321)]
    assert chunk.motion == [(5400, 0)]
    assert chunk.minutes == [(65000, 60, 12, -20, 15, 990)]
    assert chunk.modes == [
        (5000, "idle", "startup"),
        (70000, "recording", "still"),
        (80000, "idle", "walking"),
    ]
    assert chunk.hr == [(71000, 58.5, 0.75), (72000, 57.25, 1.0)]


def test_accel_timestamps_rebuild_from_deltas(chunk):
    assert len(chunk.accel) == 100
    assert chunk.accel[0] == (70000, -50, 0, 1000)
    assert chunk.accel[99] == (70000 + 99 * 20, 49, -99, 1000)


def test_a_torn_final_record_is_dropped_not_fatal(chunk):
    assert chunk.torn_bytes == 3
    assert len(chunk.hr) == 2


def test_rejects_what_is_not_a_sleep_log():
    with pytest.raises(SleepLogError):
        decode(b"{}")
    with pytest.raises(SleepLogError):
        decode(b"USL1\x02\x00\x00\x00")


def test_clock_wrap_maps_forward():
    data = FIXTURE.read_bytes()
    chunk = decode(data)
    chunk.clocks = [(0xFFFFFF00, 1000, 0)]
    assert chunk.to_unix(0x00000100) == pytest.approx(1000 + 0x200 / 1000)
