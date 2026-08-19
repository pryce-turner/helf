"""The audit log's guarantees, tested the way they will be relied on.

Every test here writes through a *raw* `sqlite3` connection wherever the point
is coverage, not convenience. That is the case application-level auditing would
miss, and the whole reason Plan 0007 is built out of triggers.
"""

import json
import sqlite3

import pytest
from sqlalchemy import text

from app import database
from app.models.food import FoodCreate, FoodUpdate
from app.repositories.food_repo import FoodRepository

pytestmark = pytest.mark.usefixtures("db_engine")


def _raw() -> sqlite3.Connection:
    """A connection the way the MCP server opens one: no SQLAlchemy at all."""
    conn = sqlite3.connect(str(database.settings.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _log(where: str = "1=1") -> list[dict]:
    with database.SessionLocal() as session:
        rows = session.execute(
            text(f"SELECT * FROM audit_log WHERE {where} ORDER BY id")  # noqa: S608
        ).mappings().all()
    return [dict(r) for r in rows]


def test_audit_log_rejects_update():
    with database.SessionLocal() as session:
        session.execute(
            text(
                "INSERT INTO audit_log (table_name, row_id, op) "
                "VALUES ('t', 1, 'INSERT')"
            )
        )
        session.commit()

    with pytest.raises(Exception, match="append-only"):
        with database.SessionLocal() as session:
            session.execute(text("UPDATE audit_log SET op = 'DELETE'"))
            session.commit()


def test_audit_log_rejects_delete():
    with database.SessionLocal() as session:
        session.execute(
            text(
                "INSERT INTO audit_log (table_name, row_id, op) "
                "VALUES ('t', 1, 'INSERT')"
            )
        )
        session.commit()

    with pytest.raises(Exception, match="append-only"):
        with database.SessionLocal() as session:
            session.execute(text("DELETE FROM audit_log"))
            session.commit()


def test_append_only_holds_for_a_raw_connection_too():
    """The interesting case. An immutability guarantee that only the ORM
    respects is not a guarantee - the agent does not go through the ORM."""
    conn = _raw()
    conn.execute("INSERT INTO audit_log (table_name, row_id, op) VALUES ('t', 1, 'INSERT')")
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM audit_log")
    conn.close()


def test_food_edit_records_both_sides():
    """The single most invisible mutation in the schema: editing a food
    rewrites every past log entry's totals, with nothing on screen to say so."""
    repo = FoodRepository()
    food = repo.create(FoodCreate(name="Egg", kcal_per_serving=78))
    repo.update(food["doc_id"], FoodUpdate(kcal_per_serving=80))

    entry = _log("table_name = 'food' AND op = 'UPDATE'")[0]
    assert json.loads(entry["old_values"])["kcal_per_serving"] == 78
    assert json.loads(entry["new_values"])["kcal_per_serving"] == 80
    assert entry["row_id"] == food["doc_id"]


def test_inserts_are_not_audited_where_the_row_is_its_own_record():
    """Creating a food is evident from the food existing. Only tables where an
    insert can destroy something - `metric` upserts, `exercises` auto-create -
    are audited on INSERT."""
    FoodRepository().create(FoodCreate(name="Egg", kcal_per_serving=78))
    assert _log("table_name = 'food'") == []


def test_metric_insert_is_audited():
    """Because `add_metric` upserts on conflict, an "insert" through the agent
    can silently replace a measurement."""
    conn = _raw()
    conn.execute("INSERT INTO observation (observed_at, source, created_at) "
                 "VALUES ('2026-08-07 08:00:00', 'manual', '2026-08-07')")
    conn.execute("INSERT INTO metric (observation_id, name, value) "
                 "VALUES (1, 'body_weight_lb', 193.0)")
    conn.commit()
    conn.close()

    entry = _log("table_name = 'metric'")[0]
    assert entry["op"] == "INSERT"
    assert json.loads(entry["new_values"])["value"] == 193.0
    assert entry["old_values"] is None


def test_cascaded_deletes_are_audited():
    """Deleting a measurement deletes its metrics by ON DELETE CASCADE. The
    rows still vanish, so they still have to be recorded."""
    conn = _raw()
    conn.execute("INSERT INTO observation (observed_at, source, created_at) "
                 "VALUES ('2026-08-07 08:00:00', 'manual', '2026-08-07')")
    conn.execute("INSERT INTO metric (observation_id, name, value) "
                 "VALUES (1, 'body_weight_lb', 193.0)")
    conn.commit()
    conn.execute("DELETE FROM observation WHERE id = 1")
    conn.commit()
    conn.close()

    deletes = _log("table_name = 'metric' AND op = 'DELETE'")
    assert len(deletes) == 1
    assert json.loads(deletes[0]["old_values"])["value"] == 193.0


def test_writes_default_to_the_app_as_actor():
    repo = FoodRepository()
    food = repo.create(FoodCreate(name="Egg", kcal_per_serving=78))
    repo.update(food["doc_id"], FoodUpdate(kcal_per_serving=80))

    assert _log("table_name = 'food'")[0]["actor"] == "app"


def test_a_writer_that_claims_an_actor_is_recorded_as_that_actor():
    """What the whole plan is for: "did I log that, or did the agent?"."""
    repo = FoodRepository()
    food = repo.create(FoodCreate(name="Egg", kcal_per_serving=78))

    conn = _raw()
    # BEGIN IMMEDIATE takes the write lock before the actor is set, which is
    # what stops another writer's rows being attributed to this one.
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE audit_actor SET actor = 'agent' WHERE id = 1")
    conn.execute("UPDATE food SET kcal_per_serving = 80 WHERE id = ?", (food["doc_id"],))
    conn.execute("UPDATE audit_actor SET actor = 'app' WHERE id = 1")
    conn.commit()
    conn.close()

    assert _log("table_name = 'food'")[0]["actor"] == "agent"


def test_the_actor_reverts_when_a_claiming_transaction_rolls_back():
    """A crash mid-write must not leave the database attributing every later
    change to the agent."""
    conn = _raw()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE audit_actor SET actor = 'agent' WHERE id = 1")
    conn.rollback()
    conn.close()

    repo = FoodRepository()
    food = repo.create(FoodCreate(name="Egg", kcal_per_serving=78))
    repo.update(food["doc_id"], FoodUpdate(kcal_per_serving=80))

    assert _log("table_name = 'food'")[0]["actor"] == "app"


def test_audit_actor_holds_exactly_one_row():
    with pytest.raises(Exception):  # noqa: B017 - CHECK constraint, driver-specific
        with database.SessionLocal() as session:
            session.execute(text("INSERT INTO audit_actor (id, actor) VALUES (2, 'x')"))
            session.commit()


def test_workout_edits_are_audited_but_not_creations():
    """`workouts` gains rows constantly and the insert is self-evident. A
    changed weight is not."""
    conn = _raw()
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Chest', '2026-08-07')")
    conn.execute("INSERT INTO exercises (name, category_id, use_count, created_at) "
                 "VALUES ('Bench', 1, 0, '2026-08-07')")
    conn.execute(
        'INSERT INTO workouts (date, exercise_id, category_id, weight, reps, "order", '
        "created_at, updated_at) VALUES ('2026-08-07', 1, 1, 185, 5, 1, '2026-08-07', '2026-08-07')"
    )
    conn.commit()
    assert _log("table_name = 'workouts'") == []

    conn.execute("UPDATE workouts SET weight = 190 WHERE id = 1")
    conn.commit()
    conn.close()

    entry = _log("table_name = 'workouts'")[0]
    assert json.loads(entry["old_values"])["weight"] == 185
    assert json.loads(entry["new_values"])["weight"] == 190
    # `order` is a reserved word; the trigger quotes it, and this is the test
    # that would have caught it not doing so.
    assert json.loads(entry["new_values"])["order"] == 1


def test_exercise_creation_is_audited():
    """The repositories auto-create exercises on reference, and so will the
    agent - a typo becomes a new exercise silently."""
    conn = _raw()
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Chest', '2026-08-07')")
    conn.execute("INSERT INTO exercises (name, category_id, use_count, created_at) "
                 "VALUES ('Bnech Press', 1, 0, '2026-08-07')")
    conn.commit()
    conn.close()

    entry = _log("table_name = 'exercises'")[0]
    assert entry["op"] == "INSERT"
    assert json.loads(entry["new_values"])["name"] == "Bnech Press"


def test_exercise_rating_is_audited():
    """A column added to an audited table is invisible to the log until the
    triggers are rebuilt, because they enumerate their columns into
    `json_object`. b3d1c07a4e21 rebuilt them to add it; d7e4f2a91b83 rebuilt
    them again to drop `is_mobility`. This is what fails if a later one
    forgets."""
    conn = _raw()
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Legs', '2026-08-10')")
    conn.execute("INSERT INTO exercises (name, category_id, use_count, created_at) "
                 "VALUES ('Hip Airplane', 1, 0, '2026-08-10')")
    conn.commit()
    conn.execute("UPDATE exercises SET rating = 5 WHERE name = 'Hip Airplane'")
    conn.commit()
    conn.close()

    entry = _log("table_name = 'exercises' AND op = 'UPDATE'")[0]
    before = json.loads(entry["old_values"])
    after = json.loads(entry["new_values"])
    assert before["rating"] is None and after["rating"] == 5
    # The dropped column is gone from the payload, not merely always-null.
    assert "is_mobility" not in before and "is_mobility" not in after


def test_the_set_level_mobility_flag_is_audited():
    """The flag moved to `workouts`, whose triggers had to learn it.

    It is a user-editable judgement about a logged set, so an edit that
    silently unflagged one would otherwise leave no trace - and the flag is
    what the agent reads the next session back from.
    """
    conn = _raw()
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Core', '2026-08-10')")
    conn.execute("INSERT INTO exercises (name, category_id, use_count, created_at) "
                 "VALUES ('Hanging Knee Raise', 1, 0, '2026-08-10')")
    conn.execute(
        "INSERT INTO workouts (date, exercise_id, category_id, reps, \"order\", "
        "created_at, updated_at) "
        "VALUES ('2026-08-11', 1, 1, 10, 1, '2026-08-11', '2026-08-11')"
    )
    conn.commit()
    conn.execute("UPDATE workouts SET is_mobility = 1 WHERE id = 1")
    conn.commit()
    conn.close()

    entry = _log("table_name = 'workouts' AND op = 'UPDATE'")[0]
    assert json.loads(entry["old_values"])["is_mobility"] == 0
    assert json.loads(entry["new_values"])["is_mobility"] == 1


def test_exercise_rating_is_bounded_for_the_raw_writer_too():
    """The Pydantic bound never sees the agent's SQL (ADR-0002); the CHECK
    is the rule both writers obey."""
    conn = _raw()
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Legs', '2026-08-10')")
    conn.execute("INSERT INTO exercises (name, category_id, use_count, created_at) "
                 "VALUES ('Cossack Squat', 1, 0, '2026-08-10')")
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE exercises SET rating = 9 WHERE name = 'Cossack Squat'")
        conn.commit()
    conn.close()
