"""The plan-0018 exercise field-configuration backfill, exercised for real.

`conftest`'s fixtures only ever migrate an *empty* database to head, which
cannot show what the migration does to rows that already exist. This builds a
scratch database at the revision before the backfill, inserts the four shapes
it has to distinguish — a movement break pool member, a movement with timed
history, one with distance history, and a plain lift — and upgrades.
"""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from app import database

#: The revision before the field configuration landed.
BEFORE = "c8e1f4a7b293"


@pytest.fixture()
def migrated(tmp_path, monkeypatch):
    """A database taken to the pre-0018 revision, seeded, then upgraded."""
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr(database.settings, "db_path", db_path)
    cfg = Config(str(database.ALEMBIC_INI))
    command.upgrade(cfg, BEFORE)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Legs', '2026-11-01')")
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at, "
        "movement_break_seconds) VALUES ('Deep Squat Hold', 1, 0, '2026-11-01', 40)"
    )
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at) "
        "VALUES ('Plank', 1, 0, '2026-11-01')"
    )
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at) "
        "VALUES ('Sled Push', 1, 0, '2026-11-01')"
    )
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at) "
        "VALUES ('Barbell Squat', 1, 0, '2026-11-01')"
    )
    # Plank has timed history; Sled Push has distance history. Both are plain
    # lifts otherwise, so these are the only things that can enable the groups.
    conn.execute(
        'INSERT INTO workouts (date, exercise_id, category_id, time, "order", '
        "created_at, updated_at) VALUES ('2026-11-02', 2, 1, '0:30', 1, "
        "'2026-11-02', '2026-11-02')"
    )
    conn.execute(
        'INSERT INTO workouts (date, exercise_id, category_id, distance, '
        'distance_unit, "order", created_at, updated_at) VALUES '
        "('2026-11-02', 3, 1, 40.0, 'm', 1, '2026-11-02', '2026-11-02')"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _exercise(conn, name: str) -> dict:
    row = conn.execute("SELECT * FROM exercises WHERE name = ?", (name,)).fetchone()
    assert row is not None
    return dict(row)


def test_a_pool_member_becomes_a_timed_movement_break(migrated):
    """The old bout column carried two facts — membership and a default — and
    both survive, now separately. The pool's reps and rest defaults are the
    ones the timer used to compute (plan 0018 §migration)."""
    row = _exercise(migrated, "Deep Squat Hold")

    assert row["movement_break_enabled"] == 1
    assert row["time_enabled"] == 1
    assert row["default_work_seconds"] == 40
    assert row["default_reps"] == 2
    # breakRest(40): min(30, max(10, round(40 / 2))).
    assert row["default_rest_seconds"] == 20
    assert row["default_rest_after_seconds"] is None
    assert "movement_break_seconds" not in row


def test_timed_history_enables_time_without_inventing_defaults(migrated):
    row = _exercise(migrated, "Plank")

    assert row["time_enabled"] == 1
    assert row["movement_break_enabled"] == 0
    assert row["default_work_seconds"] is None


def test_distance_history_enables_distance(migrated):
    row = _exercise(migrated, "Sled Push")

    assert row["distance_enabled"] == 1
    assert row["time_enabled"] == 0
    assert row["default_distance"] is None


def test_a_plain_lift_keeps_the_current_editor(migrated):
    row = _exercise(migrated, "Barbell Squat")

    assert row["reps_enabled"] == 1
    assert row["weight_enabled"] == 1
    assert row["distance_enabled"] == 0
    assert row["time_enabled"] == 0
    assert row["movement_break_enabled"] == 0
    assert row["default_reps"] is None
    assert row["default_weight_lb"] is None


def test_the_round_trip_restores_the_bout_column(tmp_path, monkeypatch):
    db_path = tmp_path / "roundtrip.db"
    monkeypatch.setattr(database.settings, "db_path", db_path)
    cfg = Config(str(database.ALEMBIC_INI))
    command.upgrade(cfg, BEFORE)
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Legs', '2026-11-01')")
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at, "
        "movement_break_seconds) VALUES ('Deep Squat Hold', 1, 0, '2026-11-01', 40)"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "head")
    command.downgrade(cfg, BEFORE)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM exercises WHERE name = 'Deep Squat Hold'").fetchone()
    assert dict(row) == {
        "id": 1,
        "name": "Deep Squat Hold",
        "category_id": 1,
        "last_used": None,
        "use_count": 0,
        "created_at": "2026-11-01",
        "rating": None,
        "form": None,
        "application": None,
        "movement_break_seconds": 40,
    }
    conn.close()
