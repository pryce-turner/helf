"""The one-queue merge, exercised for real.

`9c4e7b21f806` retires the `kind` split: `is_mobility` is backfilled from it,
mobility sessions slide above the lifting max so one session number picks out
one session in the merged namespace, and `mobility_plan.session` follows its
rows. The production shape is the one that matters — lifting sessions numbered
high, the agent's session numbered 1 — so that is what is seeded here.
"""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from app import database

#: The revision before the merge.
BEFORE = "c4a1e8b93d07"


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    """A database at BEFORE holding the production shape."""
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr(database.settings, "db_path", db_path)
    cfg = Config(str(database.ALEMBIC_INI))
    command.upgrade(cfg, BEFORE)

    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Push', '2026-11-01')")
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at) "
        "VALUES ('Bench', 1, 0, '2026-11-01')"
    )
    # Lifting sessions 7 and 8, one row each, the way the generator leaves them.
    for session_number in (7, 8):
        conn.execute(
            "INSERT INTO upcoming_workouts (session, kind, exercise_id, category_id, "
            "reps, created_at) VALUES (?, 'lifting', 1, 1, 5, '2026-11-01')",
            (session_number,),
        )
    # The agent's session, numbered 1 in its own namespace, with its plan.
    conn.execute(
        "INSERT INTO upcoming_workouts (session, kind, exercise_id, category_id, "
        "reps, created_at) VALUES (1, 'mobility', 1, 1, 10, '2026-11-01')"
    )
    conn.execute(
        "INSERT INTO mobility_plan (session, label, rationale, created_at) "
        "VALUES (1, 'Hips & low back', 'pigeon leads', '2026-11-01')"
    )
    conn.commit()
    conn.close()

    yield cfg, db_path


def _open(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def test_the_flag_is_backfilled_and_kind_is_gone(seeded):
    cfg, db_path = seeded
    command.upgrade(cfg, "head")

    conn = _open(db_path)
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(upcoming_workouts)")}
    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT session, is_mobility FROM upcoming_workouts ORDER BY id"
        )
    ]
    conn.close()

    assert "kind" not in columns
    assert "is_mobility" in columns
    # Lifting rows keep their numbers and lose nothing; the agent's rows are
    # flagged and their session slid above the lifting max (8) — the shape the
    # production database took (its mobility session 1 became 13).
    assert rows == [
        {"session": 7, "is_mobility": 0},
        {"session": 8, "is_mobility": 0},
        {"session": 9, "is_mobility": 1},
    ]


def test_the_plan_follows_its_rows(seeded):
    cfg, db_path = seeded
    command.upgrade(cfg, "head")

    conn = _open(db_path)
    plan = conn.execute("SELECT session, label FROM mobility_plan").fetchone()
    flagged = conn.execute(
        "SELECT DISTINCT session FROM upcoming_workouts WHERE is_mobility = 1"
    ).fetchone()
    conn.close()

    # Transfer and delete are keyed by session, so the two must name the same
    # number — the whole point of the renumber.
    assert plan["session"] == 9
    assert flagged["session"] == 9


def test_the_constraint_is_named(seeded):
    """An anonymous CHECK would be invisible to `alembic check` forever."""
    cfg, db_path = seeded
    command.upgrade(cfg, "head")

    conn = _open(db_path)
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'upcoming_workouts'"
    ).fetchone()[0]
    conn.close()

    assert "ck_upcoming_is_mobility" in sql


def test_the_downgrade_restores_the_split(seeded):
    cfg, db_path = seeded
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BEFORE)

    conn = _open(db_path)
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(upcoming_workouts)")}
    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT session, kind FROM upcoming_workouts ORDER BY id"
        )
    ]
    conn.close()

    assert "kind" in columns
    assert "is_mobility" not in columns
    # Flagged rows become mobility again. The session number stays 9 — the
    # downgrade does not renumber back down, which is why a round trip slides
    # the number up; the identifier is arbitrary and the split is what is
    # restored.
    assert rows == [
        {"session": 7, "kind": "lifting"},
        {"session": 8, "kind": "lifting"},
        {"session": 9, "kind": "mobility"},
    ]
