"""The MCP server, tested at the tool boundary.

The tool functions are plain functions and the server is assembled separately,
so everything here runs without an MCP client — which is the point: the
interesting failures are in the SQL and the privilege boundary, not in the
protocol.

`qs_mcp.DB_PATH` is module state read at import, so every test repoints it at
the migrated temporary database the `db_engine` fixture built.
"""

import sqlite3

import pytest
from sqlalchemy import text

from app import database
from app.mcp import qs_mcp


@pytest.fixture()
def mcp(db_engine, monkeypatch):
    monkeypatch.setattr(qs_mcp, "DB_PATH", database.settings.db_path)
    return qs_mcp


@pytest.fixture()
def catalog(mcp):
    """A category and an exercise, so `log_workout` has something to find."""
    with database.SessionLocal() as session:
        session.execute(
            text("INSERT INTO categories (name, created_at) VALUES ('Chest', '2026-08-07')")
        )
        session.execute(
            text(
                "INSERT INTO exercises (name, category_id, use_count, created_at) "
                "VALUES ('Bench Press', 1, 0, '2026-08-07')"
            )
        )
        session.commit()


# --------------------------------------------------------------------------
# The privilege boundary (ADR-0004)
# --------------------------------------------------------------------------
def test_query_cannot_write(mcp):
    """If this ever passes silently, nothing else about the security model
    holds - the read tool is the one an LLM composes SQL for."""
    result = mcp.query("UPDATE workouts SET weight = 0")
    assert "error" in result
    assert "readonly" in result["error"].lower()


def test_query_cannot_write_even_in_read_write_mode(mcp, monkeypatch):
    """Mode gates which *tools* exist. It does not loosen the connection."""
    monkeypatch.setattr(mcp, "READ_ONLY", False)
    assert "error" in mcp.query("DELETE FROM workouts")


def test_query_rejects_multiple_statements(mcp):
    result = mcp.query("SELECT 1; DROP TABLE workouts")
    assert "error" in result


def test_query_caps_rows(mcp, monkeypatch):
    monkeypatch.setattr(mcp, "MAX_ROWS", 2)
    with database.SessionLocal() as session:
        for name in ("a", "b", "c", "d"):
            session.execute(
                text("INSERT INTO categories (name, created_at) VALUES (:n, '2026-08-07')"),
                {"n": name},
            )
        session.commit()

    result = mcp.query("SELECT * FROM categories")
    assert result["row_count"] == 2
    assert result["truncated"] is True


def test_get_schema_includes_the_views(mcp):
    schema = mcp.get_schema()
    assert "CREATE VIEW v_daily_summary" in schema
    assert "CREATE TABLE" in schema


# --------------------------------------------------------------------------
# Startup checks (G1)
# --------------------------------------------------------------------------
def test_missing_database_is_fatal_at_startup(mcp, tmp_path, monkeypatch):
    """SQLite would create it, and the agent would then report an empty
    training history as fact."""
    monkeypatch.setattr(mcp, "DB_PATH", tmp_path / "nope.db")
    with pytest.raises(mcp.ConfigurationError, match="No database at"):
        mcp.check_database()
    assert not (tmp_path / "nope.db").exists()


def test_unmigrated_database_is_fatal_at_startup(mcp, tmp_path, monkeypatch):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    monkeypatch.setattr(mcp, "DB_PATH", empty)
    with pytest.raises(mcp.ConfigurationError, match="alembic upgrade head"):
        mcp.check_database()


def test_instructions_load(mcp):
    instructions = mcp.load_instructions()
    assert "pounds" in instructions
    assert "Never mix sources" in instructions


# --------------------------------------------------------------------------
# add_metric (G3)
# --------------------------------------------------------------------------
def test_unknown_metric_name_gets_a_useful_error(mcp):
    """The FK to `metric_def` turns the reference's "warn and insert anyway"
    into an opaque FOREIGN KEY failure. The agent gets the vocabulary instead."""
    result = mcp.add_metric("bodyfat", 14.2)
    assert result["ok"] is False
    assert "not a defined metric" in result["error"]
    assert "body_fat_pct" in result["valid_names"]


def test_add_metric_requires_a_value(mcp):
    assert mcp.add_metric("mood")["ok"] is False


def test_add_metric_creates_an_observation(mcp):
    result = mcp.add_metric("mood", 7, observed_at="2026-08-07T20:00:00")
    assert result["ok"] is True

    rows = mcp.query(
        "SELECT o.observed_at, o.source, o.date, m.name, m.value "
        "FROM metric m JOIN observation o ON o.id = m.observation_id"
    )["rows"]
    assert rows == [
        {
            "observed_at": "2026-08-07T20:00:00",
            "source": "manual",
            "date": "2026-08-07",
            "name": "mood",
            "value": 7.0,
        }
    ]


def test_relogging_the_same_instant_updates_in_place(mcp):
    """Idempotency used to ride on UNIQUE (observed_at, name, source), which
    Plan 0003 removed. It now comes from find-or-create on `observation` plus
    UNIQUE (observation_id, name)."""
    mcp.add_metric("mood", 7, observed_at="2026-08-07T20:00:00")
    mcp.add_metric("mood", 4, observed_at="2026-08-07T20:00:00")

    assert mcp.query("SELECT count(*) AS n FROM observation")["rows"][0]["n"] == 1
    assert mcp.query("SELECT value FROM metric")["rows"] == [{"value": 4.0}]


def test_different_sources_at_one_instant_stay_separate(mcp):
    """A bioimpedance estimate and a DEXA scan must never collapse into one
    reading, however close together they land."""
    mcp.add_metric("body_fat_pct", 20.3, observed_at="2026-03-10T09:00:00", source="openscale")
    mcp.add_metric("body_fat_pct", 14.2, observed_at="2026-03-10T09:00:00", source="bodyspec")

    assert mcp.query("SELECT count(*) AS n FROM observation")["rows"][0]["n"] == 2


def test_non_canonical_unit_warns_without_refusing(mcp):
    result = mcp.add_metric("body_weight_lb", 193, unit="kg")
    assert result["ok"] is True
    assert "canonical" in result["warnings"][0]


def test_get_metric_names_reports_what_has_data(mcp):
    """`v_metric_coverage`, not `metric_def`: a defined metric with no rows is
    a different fact from a flat series."""
    mcp.add_metric("mood", 7, observed_at="2026-08-07T20:00:00")
    by_name = {r["name"]: r for r in mcp.get_metric_names()["rows"]}
    assert by_name["mood"]["n_rows"] == 1
    assert by_name["sleep_hours"]["n_rows"] == 0


# --------------------------------------------------------------------------
# log_food (G4)
# --------------------------------------------------------------------------
def test_log_food_creates_then_reuses_a_brandless_food(mcp):
    """The reference matched `brand IS ?` against a UNIQUE that treats NULLs as
    distinct, so a brandless food duplicated on every call."""
    first = mcp.log_food("Egg", servings=2, kcal_per_serving=78, protein_g=6.3)
    second = mcp.log_food("Egg", servings=1)

    assert first["food_created"] is True
    assert second["food_created"] is False
    assert second["food_id"] == first["food_id"]
    assert mcp.query("SELECT count(*) AS n FROM food")["rows"][0]["n"] == 1


def test_log_food_rejects_an_unknown_meal(mcp):
    result = mcp.log_food("Egg", meal="elevenses")
    assert result["ok"] is False
    assert "snack" in result["valid_meals"]


def test_logged_food_reaches_the_daily_summary(mcp):
    mcp.log_food("Egg", servings=2, kcal_per_serving=78, consumed_at="2026-08-07T08:00:00")
    rows = mcp.daily_summary("2026-08-07", "2026-08-07")["rows"]
    assert rows[0]["kcal"] == 156


# --------------------------------------------------------------------------
# log_workout (G2, G6, G7)
# --------------------------------------------------------------------------
def test_log_workout_writes_flat_rows_in_order(mcp, catalog):
    """Plan 0004 §4's adapter: the tool speaks sessions, storage stays flat."""
    result = mcp.log_workout(
        [
            {"exercise": "Bench Press", "reps": 5, "weight_lb": 185},
            {"exercise": "Bench Press", "reps": 5, "weight_lb": 190},
        ],
        date="2026-08-07",
    )
    assert result["sets_logged"] == 2

    rows = mcp.query(
        'SELECT weight, reps, "order" FROM workouts ORDER BY "order"'
    )["rows"]
    assert rows == [
        {"weight": 185.0, "reps": 5, "order": 1},
        {"weight": 190.0, "reps": 5, "order": 2},
    ]


def test_a_second_session_continues_the_order(mcp, catalog):
    """`order` is per day, so appending to a day the PWA already wrote must not
    restart at 1 and collide with what is there."""
    mcp.log_workout([{"exercise": "Bench Press", "reps": 5, "weight_lb": 185}], date="2026-08-07")
    mcp.log_workout([{"exercise": "Bench Press", "reps": 5, "weight_lb": 190}], date="2026-08-07")

    assert [r["order"] for r in mcp.query('SELECT "order" FROM workouts')["rows"]] == [1, 2]


def test_exercise_matching_is_case_insensitive(mcp, catalog):
    """G6. `exercises.name` is UNIQUE but SQLite's default collation is
    case-sensitive, so "bench press" would have become a second exercise - and
    a second progression chart - silently."""
    result = mcp.log_workout(
        [{"exercise": "bench press", "reps": 5, "weight_lb": 185}], date="2026-08-07"
    )
    assert result["exercises_created"] == []
    assert mcp.query("SELECT count(*) AS n FROM exercises")["rows"][0]["n"] == 1


def test_a_new_exercise_is_created_and_named_back(mcp, catalog):
    """G7: `exercises.category_id` is NOT NULL with foreign keys enforced, so
    the reference's auto-create would have failed on its first call. The
    created list is what lets the agent notice it has just immortalised a typo."""
    result = mcp.log_workout(
        [{"exercise": "Bnech Press", "reps": 5, "weight_lb": 185}], date="2026-08-07"
    )
    assert result["exercises_created"] == ["Bnech Press"]

    row = mcp.query(
        "SELECT c.name FROM exercises e JOIN categories c ON c.id = e.category_id "
        "WHERE e.name = 'Bnech Press'"
    )["rows"][0]
    assert row["name"] == "Uncategorized"


def test_log_workout_rejects_a_set_with_no_exercise(mcp, catalog):
    result = mcp.log_workout([{"reps": 5, "weight_lb": 185}], date="2026-08-07")
    assert result["ok"] is False
    assert mcp.query("SELECT count(*) AS n FROM workouts")["rows"][0]["n"] == 0


def test_session_notes_land_in_note(mcp, catalog):
    mcp.log_workout(
        [{"exercise": "Bench Press", "reps": 5, "weight_lb": 185}],
        date="2026-08-07",
        notes="shoulder felt off",
    )
    rows = mcp.query("SELECT kind, body, source FROM note")["rows"]
    assert rows == [{"kind": "workout", "body": "shoulder felt off", "source": "agent"}]


# --------------------------------------------------------------------------
# Provenance (Plan 0007)
# --------------------------------------------------------------------------
def test_agent_writes_are_attributed_to_the_agent(mcp):
    """The whole reason 0007 landed before this plan."""
    mcp.log_food("Egg", kcal_per_serving=78)
    mcp.log_food("Egg", kcal_per_serving=99)  # resolves, does not edit

    with database.SessionLocal() as session:
        session.execute(text("UPDATE food SET kcal_per_serving = 80"))
        session.commit()

    actors = [
        r["actor"]
        for r in mcp.query("SELECT actor FROM audit_log WHERE table_name = 'food'")["rows"]
    ]
    assert actors == ["app"]  # the app's edit, correctly not the agent's

    mcp.add_metric("mood", 7, observed_at="2026-08-07T20:00:00")
    metric_actors = [
        r["actor"]
        for r in mcp.query("SELECT actor FROM audit_log WHERE table_name = 'metric'")["rows"]
    ]
    assert metric_actors == ["agent"]


def test_a_failed_write_leaves_no_partial_session(mcp, catalog, monkeypatch):
    """`_rw` rolls the whole transaction back, including the actor claim."""
    real = qs_mcp._resolve_exercise

    def explode(conn, name):
        if name == "Deadlift":
            raise RuntimeError("boom")
        return real(conn, name)

    monkeypatch.setattr(qs_mcp, "_resolve_exercise", explode)

    with pytest.raises(RuntimeError):
        mcp.log_workout(
            [
                {"exercise": "Bench Press", "reps": 5, "weight_lb": 185},
                {"exercise": "Deadlift", "reps": 5, "weight_lb": 315},
            ],
            date="2026-08-07",
        )

    assert mcp.query("SELECT count(*) AS n FROM workouts")["rows"][0]["n"] == 0
    assert mcp.query("SELECT actor FROM audit_actor")["rows"][0]["actor"] == "app"


# --------------------------------------------------------------------------
# Capability gating (§4)
# --------------------------------------------------------------------------
def test_write_tools_are_absent_in_read_only_mode(mcp, monkeypatch):
    """Unregistered, not refusing: a tool that does not exist cannot be
    attempted, argued with, or retried."""
    monkeypatch.setattr(mcp, "READ_ONLY", True)
    names = _tool_names(mcp.build_server())
    assert "query" in names
    assert "add_metric" not in names
    assert "log_workout" not in names


def test_write_tools_appear_in_read_write_mode(mcp, monkeypatch):
    monkeypatch.setattr(mcp, "READ_ONLY", False)
    names = _tool_names(mcp.build_server())
    assert {"add_metric", "add_note", "log_food", "log_workout"} <= names


def test_read_only_is_the_default_for_an_unset_variable(monkeypatch):
    """Forgetting the variable must yield the safe mode, not the permissive
    one. Re-imported because the flag is read at import time."""
    import importlib

    monkeypatch.delenv("QS_MCP_MODE", raising=False)
    assert importlib.reload(qs_mcp).READ_ONLY is True


def _tool_names(server) -> set[str]:
    import anyio

    return {tool.name for tool in anyio.run(server.list_tools)}
