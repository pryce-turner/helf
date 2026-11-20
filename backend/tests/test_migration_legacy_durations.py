"""The corrective legacy-duration backfill, exercised for real.

`b7e2d4f81a05` parsed only `m:ss`; production's legacy `time` values turned
out to be `h:mm:ss` (`0:00:45`), which it left NULL. The corrective revision
after it parses both shapes by component — with bounds — and writes **no
audit rows**: the triggers are dropped before any DML, because a backfill
UPDATE on an audited table otherwise emits one no-op row per row touched
(as the first run of b7e2 did on production, 9,487 of them, kept as history).
"""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from app import database

#: The revision before the set-tile columns; seeding here exercises both the
#: original and the corrective backfills in one upgrade.
BEFORE = "a3f9c21d7e48"


@pytest.fixture()
def migrated(tmp_path, monkeypatch):
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr(database.settings, "db_path", db_path)
    cfg = Config(str(database.ALEMBIC_INI))
    command.upgrade(cfg, BEFORE)

    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Core', '2026-11-01')")
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at) "
        "VALUES ('Plank', 1, 0, '2026-11-01')"
    )
    rows = [
        # (date, time, completed_at)
        # h:mm:ss, completed: target and performed work both backfill.
        ("2026-11-02", "0:00:45", "2026-11-02 07:00:00"),
        # m:ss, planned: target only.
        ("2026-11-03", "0:45", None),
        # h:mm:ss over the 3600s bound: left alone, not clamped.
        ("2026-11-04", "1:02:03", "2026-11-04 07:00:00"),
        # Unparseable: left alone.
        ("2026-11-05", "5+", "2026-11-05 07:00:00"),
        # h:mm:ss, completed: the production shape.
        ("2026-11-06", "0:01:00", "2026-11-06 07:00:00"),
    ]
    for date, time_value, completed_at in rows:
        conn.execute(
            'INSERT INTO workouts (date, exercise_id, category_id, time, '
            'completed_at, "order", created_at, updated_at) '
            "VALUES (?, 1, 1, ?, ?, 1, '2026-11-02', '2026-11-02')",
            (date, time_value, completed_at),
        )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _rows(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM workouts ORDER BY id")]


def test_h_mm_ss_parses_into_target_and_actual(migrated):
    first = _rows(migrated)[0]
    assert first["work_seconds"] == 45
    assert first["actual_work_seconds"] == 45


def test_m_ss_still_parses(migrated):
    planned = _rows(migrated)[1]
    assert planned["work_seconds"] == 45
    assert planned["actual_work_seconds"] is None


def test_an_out_of_bounds_duration_is_left_alone(migrated):
    over = _rows(migrated)[2]
    assert over["work_seconds"] is None
    assert over["time"] == "1:02:03"


def test_an_unparseable_time_is_left_alone(migrated):
    odd = _rows(migrated)[3]
    assert odd["work_seconds"] is None
    assert odd["time"] == "5+"


def test_the_production_shape_parses(migrated):
    production = _rows(migrated)[4]
    assert production["work_seconds"] == 60
    assert production["actual_work_seconds"] == 60


def test_the_backfills_write_no_audit_rows(migrated):
    """Triggers down before any DML: a backfill is schema maintenance, not a
    mutation, and 9,487 no-op rows say otherwise."""
    (count,) = migrated.execute(
        "SELECT COUNT(*) FROM audit_log WHERE table_name = 'workouts'"
    ).fetchone()
    assert count == 0


def _seed_and_upgrade(tmp_path, monkeypatch, rows, before=BEFORE):
    """Build at `before`, insert (reps, time, completed_at) rows, upgrade head."""
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr(database.settings, "db_path", db_path)
    cfg = Config(str(database.ALEMBIC_INI))
    command.upgrade(cfg, before)
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Core', '2026-11-01')")
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at) "
        "VALUES ('Plank', 1, 0, '2026-11-01')"
    )
    for reps, time_value, completed_at in rows:
        conn.execute(
            'INSERT INTO workouts (date, exercise_id, category_id, reps, time, '
            'completed_at, "order", created_at, updated_at) '
            "VALUES ('2026-11-02', 1, 1, ?, ?, ?, 1, '2026-11-02', '2026-11-02')",
            (reps, time_value, completed_at),
        )
    conn.commit()
    conn.close()
    return cfg, db_path


def _workout_triggers(db_path) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    names = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND name LIKE 'audit_workouts_%'"
        )
    ]
    conn.close()
    return sorted(names)


def test_a_completed_3rep_row_backfills_actual_as_a_total(tmp_path, monkeypatch):
    """`actual_work_seconds` is a TOTAL, matching `_derive_actuals`: 3 x 45s."""
    cfg, db_path = _seed_and_upgrade(
        tmp_path, monkeypatch, [(3, "0:00:45", "2026-11-02 07:00:00")]
    )
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM workouts WHERE id = 1").fetchone())
    conn.close()
    assert row["work_seconds"] == 45
    assert row["actual_work_seconds"] == 135


def test_an_unbounded_duration_is_skipped_like_any_unparseable(tmp_path, monkeypatch):
    """70:00 parses as 4200, which violates the work_seconds CHECK — skip it
    exactly like an unparseable value rather than dying mid-backfill."""
    cfg, db_path = _seed_and_upgrade(
        tmp_path, monkeypatch, [(None, "70:00", "2026-11-02 07:00:00")]
    )
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM workouts WHERE id = 1").fetchone())
    conn.close()
    assert row["work_seconds"] is None
    assert row["time"] == "70:00"
    assert _workout_triggers(db_path) == ["audit_workouts_delete", "audit_workouts_update"]


def test_a_failed_backfill_still_restores_the_triggers(tmp_path, monkeypatch):
    """Non-transactional DDL means a failure mid-migration must not leave the
    audited table un-watched: the doomed transaction is rolled back first,
    the triggers go back up, and the revision is replayable once the row is
    fixed."""
    # Seeded at b7e2 so only the corrective revision runs: reps = -1 makes
    # its total `45 * (reps or 1)` negative, which the CHECK refuses — a
    # failure after the triggers came down.
    cfg, db_path = _seed_and_upgrade(
        tmp_path,
        monkeypatch,
        [(-1, "0:00:45", "2026-11-02 07:00:00")],
        before="b7e2d4f81a05",
    )

    with pytest.raises(Exception):
        command.upgrade(cfg, "head")

    assert _workout_triggers(db_path) == ["audit_workouts_delete", "audit_workouts_update"]
    # And the corrective revision is replayable once the data is fixed:
    # its DML is the first thing it does, and the failure was row-level.
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE workouts SET reps = 3 WHERE id = 1")
    conn.commit()
    conn.close()
    command.upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM workouts WHERE id = 1").fetchone())
    conn.close()
    assert row["work_seconds"] == 45
    assert row["actual_work_seconds"] == 135
