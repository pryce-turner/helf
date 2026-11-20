"""The plan-0018 `workouts` backfill: targets stay, completions gain actuals.

Same shape as `test_migration_field_config.py`: build a scratch database at
the revision before the set-tile columns, insert the rows the backfill has to
distinguish — a completed set with reps, a completed timed set, a planned
timed set, and a set whose `time` is not a plain `m:ss` — and upgrade.
"""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from app import database

#: The revision before the set-tile columns landed.
BEFORE = "a3f9c21d7e48"


@pytest.fixture()
def migrated(tmp_path, monkeypatch):
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr(database.settings, "db_path", db_path)
    cfg = Config(str(database.ALEMBIC_INI))
    command.upgrade(cfg, BEFORE)

    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Legs', '2026-11-01')")
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at) "
        "VALUES ('Squat', 1, 0, '2026-11-01')"
    )
    rows = [
        # Completed set with reps: gains completed_reps = reps.
        "'2026-11-02', 1, 1, 5, NULL, '2026-11-02 07:00:00'",
        # Completed timed set: the time becomes the work target *and* the
        # performed work — it is what the row always claimed happened.
        "'2026-11-02', 1, 1, NULL, '1:05', '2026-11-02 08:00:00'",
        # Planned timed set: target only, nothing performed.
        "'2026-11-03', 1, 1, NULL, '0:40', NULL",
        # A time that is not a plain m:ss is left alone, not guessed at.
        "'2026-11-03', 1, 1, 3, '5+', '2026-11-03 09:00:00'",
    ]
    for values in rows:
        conn.execute(
            'INSERT INTO workouts (date, exercise_id, category_id, reps, time, '
            f'completed_at, "order", created_at, updated_at) VALUES ({values}, '
            "1, '2026-11-02', '2026-11-02')"
        )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _rows(conn) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM workouts ORDER BY id"
        ).fetchall()
    ]


def test_completed_sets_gain_completed_reps(migrated):
    completed, _, _, _ = _rows(migrated)

    assert completed["completed_reps"] == 5
    assert completed["ended_early"] == 0
    # Not a timed set: no work fields invented.
    assert completed["work_seconds"] is None


def test_a_completed_timed_set_gets_target_and_actual_work(migrated):
    _, timed, _, _ = _rows(migrated)

    assert timed["work_seconds"] == 65
    assert timed["actual_work_seconds"] == 65
    assert timed["completed_reps"] is None  # a timed hold is not a rep
    # The legacy string is kept while consumers move off it.
    assert timed["time"] == "1:05"


def test_a_planned_timed_set_gains_only_the_target(migrated):
    _, _, planned, _ = _rows(migrated)

    assert planned["work_seconds"] == 40
    assert planned["actual_work_seconds"] is None
    assert planned["completed_reps"] is None


def test_an_unparseable_time_is_left_alone(migrated):
    _, _, _, odd = _rows(migrated)

    assert odd["work_seconds"] is None
    assert odd["time"] == "5+"
    # Still a completed set with reps, though.
    assert odd["completed_reps"] == 3


def test_a_failed_backfill_still_restores_the_triggers(tmp_path, monkeypatch):
    """Non-transactional DDL means a failure mid-migration must not leave the
    audited table un-watched: the triggers go back up in `finally`, and the
    revision marker honestly stays behind for the re-run."""
    db_path = tmp_path / "roundtrip.db"
    monkeypatch.setattr(database.settings, "db_path", db_path)
    cfg = Config(str(database.ALEMBIC_INI))
    command.upgrade(cfg, BEFORE)
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Legs', '2026-11-01')")
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at) "
        "VALUES ('Squat', 1, 0, '2026-11-01')"
    )
    # reps = -1: backfilled into completed_reps, the CHECK refuses it — a
    # failure after the triggers came down.
    conn.execute(
        'INSERT INTO workouts (date, exercise_id, category_id, reps, time, '
        'completed_at, "order", created_at, updated_at) VALUES '
        "('2026-11-02', 1, 1, -1, '0:30', '2026-11-02 07:00:00', 1, "
        "'2026-11-02', '2026-11-02')"
    )
    conn.commit()
    conn.close()

    with pytest.raises(Exception):
        command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    triggers = sorted(
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND name LIKE 'audit_workouts_%'"
        )
    )
    version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    conn.close()
    assert triggers == ["audit_workouts_delete", "audit_workouts_update"]
    # The failure is reported, not half-applied: the operator re-runs after
    # fixing the row.
    assert version == BEFORE

    # The re-run is the whole point: the columns ADDed by the failed attempt
    # are skipped, the backfill completes, and the chain reaches head.
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE workouts SET reps = 3 WHERE id = 1")
    conn.commit()
    conn.close()
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM workouts WHERE id = 1").fetchone())
    triggers = sorted(
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND name LIKE 'audit_workouts_%'"
        )
    )
    version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    conn.close()

    assert version == "c4a1e8b93d07"
    assert triggers == ["audit_workouts_delete", "audit_workouts_update"]
    assert row["completed_reps"] == 3
    assert row["work_seconds"] == 30
    # The total, matching `_derive_actuals`: 3 x 30s.
    assert row["actual_work_seconds"] == 90


def test_the_round_trip_leaves_the_table_as_it_was(tmp_path, monkeypatch):
    db_path = tmp_path / "roundtrip.db"
    monkeypatch.setattr(database.settings, "db_path", db_path)
    cfg = Config(str(database.ALEMBIC_INI))
    command.upgrade(cfg, BEFORE)
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Legs', '2026-11-01')")
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at) "
        "VALUES ('Squat', 1, 0, '2026-11-01')"
    )
    conn.execute(
        'INSERT INTO workouts (date, exercise_id, category_id, reps, time, '
        'completed_at, "order", created_at, updated_at) VALUES '
        "('2026-11-02', 1, 1, 5, '0:30', '2026-11-02 07:00:00', 1, "
        "'2026-11-02', '2026-11-02')"
    )
    conn.commit()
    before = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'view' AND name = 'v_daily_summary'"
    ).fetchone()[0]
    conn.close()

    command.upgrade(cfg, "head")
    command.downgrade(cfg, BEFORE)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM workouts WHERE id = 1").fetchone())
    for column in (
        "work_seconds",
        "rest_seconds",
        "rest_after_seconds",
        "completed_reps",
        "actual_work_seconds",
        "actual_rest_seconds",
        "actual_rest_after_seconds",
        "ended_early",
    ):
        assert column not in row
    # The view is back to counting every row, performed or not.
    after = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'view' AND name = 'v_daily_summary'"
    ).fetchone()[0]
    assert after == before
    conn.close()
