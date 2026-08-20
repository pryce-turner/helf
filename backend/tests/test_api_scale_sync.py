"""The scale drain endpoint - plan 0015 §4.

The properties worth testing here are the ones that make it safe to hand the
endpoint the same thirty readings every time: the source it files them under,
and that a replay is a no-op rather than duplicate history.
"""

from datetime import datetime, timedelta

import pytest

from app.utils.date_helpers import PACIFIC_TZ

pytestmark = pytest.mark.usefixtures("db_engine")


def _reading(moment: datetime, weight: float = 190.0, **extra) -> dict:
    return {
        "timestamp": moment.isoformat(),
        "date": moment.date().isoformat(),
        "weight": weight,
        **extra,
    }


def test_drain_imports_then_treats_a_replay_as_already_held(client):
    now = datetime.now(PACIFIC_TZ).replace(microsecond=0)
    readings = [_reading(now - timedelta(days=n), 190.0 + n) for n in range(3)]

    first = client.post(
        "/api/body-composition/sync/scale", json={"readings": readings}
    )
    assert first.status_code == 200
    assert first.json() == {
        "readings_received": 3,
        "imported": 3,
        "skipped": 0,
    }

    # The scale replays its whole ring on every connect, so this is the normal
    # case rather than an edge case - and it must not write anything.
    replay = client.post(
        "/api/body-composition/sync/scale", json={"readings": readings}
    )
    assert replay.status_code == 200
    assert replay.json() == {
        "readings_received": 3,
        "imported": 0,
        "skipped": 3,
    }

    assert len(client.get("/api/body-composition/").json()) == 3


def test_a_drain_mixing_old_and_new_imports_only_the_new(client):
    now = datetime.now(PACIFIC_TZ).replace(microsecond=0)
    old = [_reading(now - timedelta(days=n)) for n in range(2, 5)]
    client.post("/api/body-composition/sync/scale", json={"readings": old})

    mixed = old + [_reading(now - timedelta(days=n)) for n in range(0, 2)]
    result = client.post(
        "/api/body-composition/sync/scale", json={"readings": mixed}
    )
    assert result.json() == {
        "readings_received": 5,
        "imported": 2,
        "skipped": 3,
    }


def test_drained_readings_are_filed_under_openscale_not_manual(client):
    """The whole reason this endpoint exists rather than reusing `POST /`.

    `POST /` writes `source='manual'`, which would split the openScale series
    at whatever date the PWA went live - and do it silently, since a manual
    entry is a legitimate thing for that route to produce.
    """
    now = datetime.now(PACIFIC_TZ).replace(microsecond=0)
    client.post(
        "/api/body-composition/sync/scale",
        json={
            "readings": [
                _reading(now - timedelta(days=1), 190.0),
                _reading(now, 188.4),
            ]
        },
    )

    latest = client.get("/api/body-composition/latest").json()
    assert latest["source"] == "openscale"

    # Two readings, because `primary_source` deliberately requires a series
    # with enough history to have a direction - one point is not a trend.
    stats = client.get("/api/body-composition/stats").json()
    assert stats["primary_source"] == "openscale"
    assert stats["weight_change"] == pytest.approx(-1.6)


def test_a_drained_reading_and_a_manual_entry_at_one_instant_coexist(client):
    """Different instruments, so `UNIQUE (observed_at, source)` keeps both.

    This is the behaviour plan 0010 introduced deliberately: duplicate
    detection is per instrument, because a hand-entered weight and a scale
    reading at the same second are two observations, not one.
    """
    now = datetime.now(PACIFIC_TZ).replace(microsecond=0)

    manual = client.post("/api/body-composition/", json=_reading(now, 190.0))
    assert manual.status_code == 201

    drained = client.post(
        "/api/body-composition/sync/scale",
        json={"readings": [_reading(now, 190.0)]},
    )
    assert drained.json()["imported"] == 1

    assert len(client.get("/api/body-composition/").json()) == 2


def test_an_empty_drain_is_valid_and_writes_nothing(client):
    """A connect that finds an empty ring is not an error."""
    result = client.post(
        "/api/body-composition/sync/scale", json={"readings": []}
    )
    assert result.status_code == 200
    assert result.json() == {
        "readings_received": 0,
        "imported": 0,
        "skipped": 0,
    }


def test_sorting_by_ingestion_finds_a_reading_a_bad_clock_hid(client):
    """The BF720 stamped a reading 2025-01-01 while being written in 2026-08.

    A scale that has been reset reports its factory clock, so a weighing taken
    today lands years away in observed order - buried mid-history where nobody
    scrolls. Ingestion order puts it back on top, which is the only way to find
    it and delete it.
    """
    now = datetime.now(PACIFIC_TZ).replace(microsecond=0)
    stale_clock = now.replace(year=2025, month=1, day=1)

    client.post(
        "/api/body-composition/sync/scale",
        json={
            "readings": [
                _reading(now - timedelta(days=2), 190.0),
                _reading(now - timedelta(days=1), 191.0),
            ]
        },
    )
    # Written last, but claims to be the oldest.
    client.post(
        "/api/body-composition/sync/scale",
        json={"readings": [_reading(stale_clock, 197.9)]},
    )

    by_observed = client.get("/api/body-composition/?sort=observed").json()
    assert by_observed[0]["weight"] == 191.0
    assert by_observed[-1]["weight"] == 197.9, "the bad row sinks to the bottom"

    by_ingested = client.get("/api/body-composition/?sort=ingested").json()
    assert by_ingested[0]["weight"] == 197.9, "the bad row surfaces"

    # Both timestamps travel with the row, which is what makes the gap visible.
    assert by_ingested[0]["timestamp"].startswith("2025-01-01")
    assert by_ingested[0]["created_at"] > by_ingested[0]["timestamp"]


def test_an_unknown_sort_is_rejected_rather_than_interpolated(client):
    """The column is interpolated into the statement, so this must not reach it."""
    assert client.get("/api/body-composition/?sort=observed_at; DROP TABLE").status_code == 422
    assert client.get("/api/body-composition/?sort=nonsense").status_code == 422
