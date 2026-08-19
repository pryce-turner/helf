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


def test_mobility_tools_are_present_in_read_only_mode(mcp, monkeypatch):
    """The scoped exception (Plan 0012 §5).

    The mobility loop's whole value is the agent writing the next session, so
    its write tool is registered in both modes. If this ever stops being
    deliberate, the failure is silent — the tab just never leaves the "no
    session ready" state — which is why it is asserted rather than assumed.
    """
    monkeypatch.setattr(mcp, "READ_ONLY", True)
    names = _tool_names(mcp.build_server())

    assert "read_latest_mobility_session" in names
    assert "read_pending_mobility_session" in names
    assert "write_next_mobility_session" in names
    assert "update_mobility_movement" in names
    # The exception is scoped. Everything else still obeys the mode.
    assert "log_workout" not in names
    assert "add_metric" not in names


# --------------------------------------------------------------------------
# The mobility loop
# --------------------------------------------------------------------------
def _run_session(mcp, date: str, comment: str | None = None) -> None:
    """Put a logged mobility day in the database, the way a transfer would."""
    with database.SessionLocal() as session:
        session.execute(
            text(
                "INSERT INTO categories (name, created_at) VALUES ('Core', '2026-08-07')"
            )
        )
        session.execute(
            text(
                "INSERT INTO exercises (name, category_id, use_count, "
                "created_at) VALUES ('QL Raise', 1, 0, '2026-08-07')"
            )
        )
        session.execute(
            text(
                'INSERT INTO workouts (date, exercise_id, category_id, reps, comment, '
                '"order", is_mobility, created_at, updated_at) '
                "VALUES (:d, 1, 1, 8, :c, 1, 1, '2026-08-07', '2026-08-07')"
            ),
            {"d": date, "c": comment},
        )
        session.execute(
            text(
                "INSERT INTO note (noted_at, kind, body, source) "
                "VALUES (:n, 'mobility_session', 'held QL steady', 'agent')"
            ),
            {"n": f"{date}T12:00:00"},
        )
        session.commit()


def test_read_latest_says_so_when_nothing_has_been_logged(mcp):
    result = mcp.read_latest_mobility_session()

    assert result["found"] is False
    # An agent told "no data" invents a first session from nothing; told where
    # the movements and their notes are, it reads them.
    assert "exercises" in result["hint"]
    assert "form" in result["hint"] and "application" in result["hint"]


def test_read_latest_returns_the_sets_and_their_comments(mcp):
    _run_session(mcp, "2026-08-11", comment="8 then 10, up to 35 next")

    result = mcp.read_latest_mobility_session()

    assert result["found"] is True
    assert result["date"] == "2026-08-11"
    assert result["rationale"] == "held QL steady"
    assert result["sets"][0]["exercise"] == "QL Raise"
    assert result["sets"][0]["comment"] == "8 then 10, up to 35 next"


def test_read_latest_ignores_the_same_movement_used_as_lifting(mcp):
    """The same movement, two objectives — and only the set says which.

    A mobility routine borrows movements that are also lifting movements, so
    "the last day containing a mobility exercise" finds lifting days too:
    2026-06-25 in the real database is a pigeon squat logged beside a Romanian
    deadlift. The flag is on the set, so the later *unflagged* day is not a
    mobility session even though it uses the very same exercise row.
    """
    _run_session(mcp, "2026-08-11")
    with database.SessionLocal() as session:
        session.execute(
            text(
                'INSERT INTO workouts (date, exercise_id, category_id, reps, "order", '
                "is_mobility, created_at, updated_at) "
                "VALUES ('2026-08-12', 1, 1, 8, 1, 0, '2026-08-07', '2026-08-07')"
            )
        )
        session.commit()

    assert mcp.read_latest_mobility_session()["date"] == "2026-08-11"


def test_read_latest_returns_only_the_mobility_sets_of_a_mixed_day(mcp):
    """A mobility session run alongside lifting is one day, two sessions.

    Returning the whole day would hand the agent a shoulder workout as the
    thing to adjust. The real 2026-08-13 is exactly this shape: two sets of
    rehab work opening a twelve-set shoulder day.
    """
    _run_session(mcp, "2026-08-11")
    with database.SessionLocal() as session:
        session.execute(
            text("INSERT INTO categories (name, created_at) VALUES ('Push', '2026-08-07')")
        )
        session.execute(
            text(
                "INSERT INTO exercises (name, category_id, use_count, created_at) "
                "VALUES ('Overhead Press', 2, 0, '2026-08-07')"
            )
        )
        session.execute(
            text(
                'INSERT INTO workouts (date, exercise_id, category_id, reps, "order", '
                "is_mobility, created_at, updated_at) "
                "VALUES ('2026-08-11', 2, 2, 3, 2, 0, '2026-08-07', '2026-08-07')"
            )
        )
        session.commit()

    result = mcp.read_latest_mobility_session()

    assert result["date"] == "2026-08-11"
    assert [row["exercise"] for row in result["sets"]] == ["QL Raise"]


def test_write_next_expands_sets_into_rows(mcp):
    result = mcp.write_next_mobility_session(
        items=[{"exercise": "QL Raise", "sets": 2, "reps": 8, "weight_lb": 30}],
        rationale="up to 35 next time",
    )

    assert result["ok"] is True
    assert result["sets_written"] == 2
    assert result["movements"] == 1

    rows = mcp.query(
        "SELECT reps, weight, kind FROM upcoming_workouts ORDER BY id"
    )["rows"]
    assert rows == [
        {"reps": 8, "weight": 30.0, "kind": "mobility"},
        {"reps": 8, "weight": 30.0, "kind": "mobility"},
    ]


def test_write_next_records_nothing_about_mobility_on_the_exercise(mcp):
    """Prescribing a movement says nothing about the movement itself.

    It used to flag an invented exercise `is_mobility = 1`, which made the
    pool grow by side effect and could not express the same movement being
    used two ways. The intent rides on the planned row's `kind` and lands on
    `workouts.is_mobility` at transfer.
    """
    mcp.write_next_mobility_session(
        items=[{"exercise": "Jefferson Curl", "sets": 1, "reps": 5}],
        rationale="probing the range unloaded",
    )

    columns = mcp.query("SELECT * FROM exercises WHERE name = 'Jefferson Curl'")
    assert columns["rows"][0]["name"] == "Jefferson Curl"
    assert "is_mobility" not in columns["rows"][0]


def test_write_next_replaces_the_pending_session(mcp):
    mcp.write_next_mobility_session(
        items=[{"exercise": "QL Raise", "sets": 3, "reps": 8}], rationale="first"
    )
    result = mcp.write_next_mobility_session(
        items=[{"exercise": "QL Raise", "sets": 2, "reps": 8}], rationale="second"
    )

    assert result["replaced_pending_rows"] == 3
    assert mcp.query("SELECT count(*) n FROM upcoming_workouts")["rows"] == [{"n": 2}]
    assert mcp.query("SELECT body FROM note WHERE kind = 'mobility_plan'")["rows"] == [
        {"body": "second"}
    ]


def test_write_next_leaves_lifting_rows_untouched(mcp):
    """Same table, and the DELETE that replaces the pending session is one
    missing predicate away from clearing the user's whole program."""
    with database.SessionLocal() as session:
        session.execute(
            text("INSERT INTO categories (name, created_at) VALUES ('Push', '2026-08-07')")
        )
        session.execute(
            text(
                "INSERT INTO exercises (name, category_id, use_count, created_at) "
                "VALUES ('Bench', 1, 0, '2026-08-07')"
            )
        )
        session.execute(
            text(
                "INSERT INTO upcoming_workouts (session, kind, exercise_id, "
                "category_id, reps, created_at) "
                "VALUES (1, 'lifting', 1, 1, 5, '2026-08-07')"
            )
        )
        session.commit()

    mcp.write_next_mobility_session(
        items=[{"exercise": "QL Raise", "sets": 1, "reps": 8}], rationale="one set"
    )

    assert mcp.query(
        "SELECT count(*) n FROM upcoming_workouts WHERE kind = 'lifting'"
    )["rows"] == [{"n": 1}]


def test_write_next_requires_a_rationale(mcp):
    result = mcp.write_next_mobility_session(
        items=[{"exercise": "QL Raise", "reps": 8}], rationale="   "
    )

    assert result["ok"] is False
    assert mcp.query("SELECT count(*) n FROM upcoming_workouts")["rows"] == [{"n": 0}]


def test_write_next_rejects_an_empty_session(mcp):
    assert mcp.write_next_mobility_session(items=[], rationale="nothing")["ok"] is False


def test_write_next_is_attributed_to_the_agent(mcp):
    """The actor claim is what `_rw`'s BEGIN IMMEDIATE dance exists for.

    Two audited operations here, and note which: creating an exercise is an
    INSERT on `exercises`, and replacing the rationale is a DELETE on `note`.
    Ordinary note *inserts* are not audited at all — 0007 logs INSERTs only on
    `metric` and `exercises`, where an insert can silently replace or invent
    something.
    """
    mcp.write_next_mobility_session(
        items=[{"exercise": "QL Raise", "sets": 1, "reps": 8}], rationale="first"
    )
    mcp.write_next_mobility_session(
        items=[{"exercise": "QL Raise", "sets": 1, "reps": 8}], rationale="second"
    )

    logged = mcp.query(
        "SELECT table_name, op, actor FROM audit_log ORDER BY id"
    )["rows"]

    assert {"table_name": "exercises", "op": "INSERT", "actor": "agent"} in logged
    assert {"table_name": "note", "op": "DELETE", "actor": "agent"} in logged
    # The claim is released inside the same transaction, so nothing later is
    # attributed to the agent by accident.
    assert mcp.query("SELECT actor FROM audit_actor")["rows"] == [{"actor": "app"}]


# --------------------------------------------------------------------------
# What is on deck
# --------------------------------------------------------------------------
def test_read_pending_says_so_when_nothing_is_waiting(mcp):
    assert mcp.read_pending_mobility_session() == {"ok": True, "pending": False}


def test_read_pending_returns_the_routine_in_prescribed_order(mcp):
    mcp.write_next_mobility_session(
        items=[
            {"exercise": "Decline Bicycle Crunch", "sets": 1, "reps": 20},
            {"exercise": "QL Raise", "sets": 2, "reps": 8, "comment": "each side"},
        ],
        rationale="core first, then the QL",
    )

    result = mcp.read_pending_mobility_session()

    assert result["pending"] is True
    assert result["rationale"] == "core first, then the QL"
    # One row per set, in insertion order. The table has no `order` column, so
    # nothing else carries the sequence the routine is to be performed in.
    assert [item["exercise"] for item in result["items"]] == [
        "Decline Bicycle Crunch",
        "QL Raise",
        "QL Raise",
    ]
    assert result["items"][1]["comment"] == "each side"


def test_read_pending_ignores_a_rationale_with_no_items(mcp):
    """A plan note on its own is a leftover, not a session.

    Reporting it would describe a routine the user cannot see — the same rule
    `MobilityService.get_pending` follows on the app side.
    """
    mcp.write_next_mobility_session(
        items=[{"exercise": "QL Raise", "reps": 8}], rationale="stale"
    )
    with database.SessionLocal() as session:
        session.execute(text("DELETE FROM upcoming_workouts"))
        session.commit()

    assert mcp.read_pending_mobility_session()["pending"] is False


def test_read_pending_ignores_a_pending_lifting_session(mcp):
    """`session = 1` is the mobility slot, but lifting numbers its sessions
    from 1 as well. `kind` is what separates them, not the number."""
    mcp.write_next_mobility_session(
        items=[{"exercise": "QL Raise", "reps": 8}], rationale="the mobility one"
    )
    with database.SessionLocal() as session:
        session.execute(
            text(
                "INSERT INTO upcoming_workouts (session, kind, exercise_id, "
                "category_id, reps, created_at) "
                "VALUES (1, 'lifting', 1, 1, 5, '2026-08-13')"
            )
        )
        session.commit()

    result = mcp.read_pending_mobility_session()

    assert len(result["items"]) == 1
    assert result["items"][0]["reps"] == 8


# --------------------------------------------------------------------------
# What a session taught you about a movement
# --------------------------------------------------------------------------
@pytest.fixture()
def movement(mcp):
    """A movement that has been performed as mobility work, with notes to supersede.

    It has to have been *run*, not merely prescribed: the tool gates on a
    logged set with `is_mobility = 1`, there being no flag on the exercise to
    gate on any more.
    """
    _run_session(mcp, "2026-08-11")
    with database.SessionLocal() as session:
        session.execute(
            text(
                "UPDATE exercises SET form = 'hold the brace', "
                "application = 'second set fades -> load too high -> drop 5lb', "
                "rating = 3 WHERE name = 'QL Raise'"
            )
        )
        session.commit()
    return mcp.query("SELECT id FROM exercises WHERE name = 'QL Raise'")["rows"][0]["id"]


def test_update_movement_supersedes_the_application(mcp, movement):
    result = mcp.update_mobility_movement(
        movement, application="left lags right -> asymmetry -> lead with the left"
    )

    assert result["ok"] is True
    assert result["updated"] == ["application"]
    # The previous value comes back because each field is current state — once
    # replaced, what it used to say exists only in `audit_log`.
    assert result["previous"] == {
        "form": "hold the brace",
        "application": "second set fades -> load too high -> drop 5lb",
        "rating": 3,
    }


def test_writing_application_cannot_damage_form(mcp, movement):
    """The whole point of the split (e2b9c4d17a05).

    One blob meant the agent re-emitted the setup instructions from memory
    every time it recorded something learned, and a slip silently rewrote
    reference material it never meant to touch.
    """
    mcp.update_mobility_movement(movement, application="rewritten entirely")

    assert mcp.query(f"SELECT form FROM exercises WHERE id = {movement}")["rows"] == [
        {"form": "hold the brace"}
    ]


def test_update_movement_leaves_an_omitted_field_alone(mcp, movement):
    mcp.update_mobility_movement(movement, rating=5)

    assert mcp.query(
        f"SELECT form, application, rating FROM exercises WHERE id = {movement}"
    )["rows"] == [
        {
            "form": "hold the brace",
            "application": "second set fades -> load too high -> drop 5lb",
            "rating": 5,
        }
    ]


def test_update_movement_needs_something_to_write(mcp, movement):
    assert mcp.update_mobility_movement(movement)["ok"] is False


def test_update_movement_refuses_to_blank_a_field(mcp, movement):
    """Blanking discards how the movement is performed. Omitting the field is
    how you leave it alone, and the two are easy to confuse from the far side
    of a tool call."""
    result = mcp.update_mobility_movement(movement, application="   ")

    assert result["ok"] is False
    assert mcp.query(
        f"SELECT application FROM exercises WHERE id = {movement}"
    )["rows"] == [
        {"application": "second set fades -> load too high -> drop 5lb"}
    ]


def test_update_movement_refuses_a_rating_outside_the_scale(mcp, movement):
    """The CHECK constraint would catch this, but as an opaque IntegrityError.
    The agent needs to be told the scale, not that a constraint exists."""
    result = mcp.update_mobility_movement(movement, rating=0)

    assert result["ok"] is False
    assert "1-5" in result["error"]


def test_update_movement_refuses_an_unknown_exercise(mcp, movement):
    assert mcp.update_mobility_movement(9999, rating=4)["ok"] is False


def test_update_movement_refuses_a_movement_never_used_that_way(mcp, catalog):
    """A tool that could write notes at any movement would be a general
    exercise editor with a mobility-shaped name. A movement joins the pool by
    having been performed as mobility work — the judgement is in the log."""
    bench = mcp.query("SELECT id FROM exercises WHERE name = 'Bench Press'")["rows"][0]

    result = mcp.update_mobility_movement(bench["id"], rating=5)

    assert result["ok"] is False
    assert "never been logged as mobility work" in result["error"]
    assert mcp.query("SELECT rating FROM exercises WHERE name = 'Bench Press'")[
        "rows"
    ] == [{"rating": None}]


def test_update_movement_is_attributed_to_the_agent(mcp, movement):
    mcp.update_mobility_movement(movement, rating=1)

    logged = mcp.query("SELECT table_name, op, actor FROM audit_log ORDER BY id")["rows"]

    assert {"table_name": "exercises", "op": "UPDATE", "actor": "agent"} in logged
    assert mcp.query("SELECT actor FROM audit_actor")["rows"] == [{"actor": "app"}]


def test_read_only_is_the_default_for_an_unset_variable(monkeypatch):
    """Forgetting the variable must yield the safe mode, not the permissive
    one. Re-imported because the flag is read at import time."""
    import importlib

    monkeypatch.delenv("QS_MCP_MODE", raising=False)
    assert importlib.reload(qs_mcp).READ_ONLY is True


def test_instructions_are_found_from_the_container_layout(tmp_path, monkeypatch):
    """The repo nests one level deeper than the image, and the old
    `parents[3]` encoded the repo's depth as a constant.

    Repo is `<root>/backend/app/mcp/qs_mcp.py`; the image is `/app/app/mcp/`.
    `parents[3]` resolved to `/docs/design/...` in the container, and since
    missing instructions are fatal the server could not start in production at
    all — silently, because nothing outside a container exercised that path.
    This reproduces the container layout rather than trusting the arithmetic.
    """
    monkeypatch.delenv("QS_MCP_INSTRUCTIONS", raising=False)

    root = tmp_path / "app"
    module = root / "app" / "mcp" / "qs_mcp.py"
    module.parent.mkdir(parents=True)
    module.write_text("")
    instructions = root / "docs" / "design" / "mcp-instructions.md"
    instructions.parent.mkdir(parents=True)
    instructions.write_text("# instructions")

    monkeypatch.setattr(qs_mcp, "__file__", str(module))
    assert qs_mcp._find_instructions() == instructions


def test_instructions_path_can_be_overridden(tmp_path, monkeypatch):
    """For a layout neither the repo nor the image anticipates."""
    elsewhere = tmp_path / "custom.md"
    elsewhere.write_text("# instructions")
    monkeypatch.setenv("QS_MCP_INSTRUCTIONS", str(elsewhere))

    assert qs_mcp._find_instructions() == elsewhere


def test_unknown_transport_is_refused(monkeypatch):
    """A typo in `QS_MCP_TRANSPORT` must not silently fall back to stdio.

    A container that quietly served stdio would look healthy — the process
    stays up — while nothing could ever reach it over the network.
    """
    monkeypatch.setenv("QS_MCP_TRANSPORT", "http")  # the plausible wrong name

    with pytest.raises(qs_mcp.ConfigurationError, match="streamable-http"):
        qs_mcp.main()


def _tool_names(server) -> set[str]:
    import anyio

    return {tool.name for tool in anyio.run(server.list_tools)}
