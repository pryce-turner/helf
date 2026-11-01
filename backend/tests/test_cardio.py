"""Cardio: an exercise carries a default unit, and its sets carry time + amount.

`exercises.cardio_unit` being non-null *is* what makes an exercise cardio -
there is no separate flag that could disagree with it. Each set copies the
unit onto `workouts.amount_unit` so that changing an exercise's default later
does not relabel the history logged under it (plan 0017).
"""

import json
import sqlite3

import pytest

import app.database as database

pytestmark = pytest.mark.usefixtures("db_engine")


def _raw() -> sqlite3.Connection:
    conn = sqlite3.connect(database.settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_raw(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO categories (name, created_at) VALUES ('Cardio', '2026-11-01')")
    conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at, cardio_unit) "
        "VALUES ('Stairmaster', 1, 0, '2026-11-01', 'floors')"
    )
    conn.execute(
        'INSERT INTO workouts (date, exercise_id, category_id, "order", created_at, '
        "updated_at, duration_s, amount, amount_unit) VALUES "
        "('2026-11-01', 1, 1, 1, '2026-11-01', '2026-11-01', 1200, 60, 'floors')"
    )
    conn.commit()


# --- exercises ---------------------------------------------------------------


def test_a_new_exercise_is_resistance_unless_given_a_unit(client):
    created = client.post(
        "/api/exercises/", json={"name": "Bench", "category": "Push"}
    ).json()
    assert created["cardio_unit"] is None


def test_a_cardio_exercise_round_trips_its_unit(client):
    created = client.post(
        "/api/exercises/",
        json={"name": "Stairmaster", "category": "Cardio", "cardio_unit": "floors"},
    )
    assert created.status_code == 201
    assert created.json()["cardio_unit"] == "floors"
    assert client.get("/api/exercises/Stairmaster").json()["cardio_unit"] == "floors"


def test_an_unknown_unit_is_refused(client):
    response = client.post(
        "/api/exercises/",
        json={"name": "Treadmill", "category": "Cardio", "cardio_unit": "furlongs"},
    )
    assert response.status_code == 422


def test_editing_an_exercise_without_the_unit_leaves_it_alone(client):
    created = client.post(
        "/api/exercises/",
        json={"name": "Run", "category": "Cardio", "cardio_unit": "miles"},
    ).json()
    edited = client.put(f"/api/exercises/{created['doc_id']}", json={"rating": 4})
    assert edited.json()["cardio_unit"] == "miles"


def test_an_explicit_null_unit_makes_it_resistance_again(client):
    created = client.post(
        "/api/exercises/",
        json={"name": "Sled Push", "category": "Legs", "cardio_unit": "meters"},
    ).json()
    edited = client.put(
        f"/api/exercises/{created['doc_id']}", json={"cardio_unit": None}
    )
    assert edited.json()["cardio_unit"] is None


# --- sets --------------------------------------------------------------------


def test_a_cardio_set_round_trips_time_amount_and_unit(client):
    created = client.post(
        "/api/workouts/",
        json={
            "date": "2026-11-01",
            "exercise": "Run",
            "category": "Cardio",
            "duration_s": 1935,
            "amount": 3.1,
            "amount_unit": "miles",
        },
    )
    assert created.status_code == 201
    fetched = client.get("/api/workouts/?date=2026-11-01").json()[0]
    assert (fetched["duration_s"], fetched["amount"], fetched["amount_unit"]) == (
        1935,
        3.1,
        "miles",
    )
    assert fetched["weight"] is None and fetched["reps"] is None


def test_a_set_with_an_unknown_unit_is_refused(client):
    response = client.post(
        "/api/workouts/",
        json={
            "date": "2026-11-01",
            "exercise": "Run",
            "category": "Cardio",
            "amount": 3,
            "amount_unit": "leagues",
        },
    )
    assert response.status_code == 422


def test_a_negative_duration_is_refused(client):
    response = client.post(
        "/api/workouts/",
        json={
            "date": "2026-11-01",
            "exercise": "Run",
            "category": "Cardio",
            "duration_s": -5,
        },
    )
    assert response.status_code == 422


def test_editing_a_set_replaces_its_cardio_fields(client):
    created = client.post(
        "/api/workouts/",
        json={
            "date": "2026-11-01",
            "exercise": "Stairmaster",
            "category": "Cardio",
            "duration_s": 600,
            "amount": 30,
            "amount_unit": "floors",
        },
    ).json()
    edited = client.put(
        f"/api/workouts/{created['doc_id']}",
        json={
            "date": "2026-11-01",
            "exercise": "Stairmaster",
            "category": "Cardio",
            "duration_s": 900,
            "amount": 45,
            "amount_unit": "floors",
        },
    ).json()
    assert (edited["duration_s"], edited["amount"]) == (900, 45)


def test_copying_a_day_carries_the_cardio_fields(client):
    client.post(
        "/api/workouts/",
        json={
            "date": "2026-11-01",
            "exercise": "Run",
            "category": "Cardio",
            "duration_s": 1800,
            "amount": 3,
            "amount_unit": "miles",
        },
    )
    copied = client.post(
        "/api/workouts/date/2026-11-01/copy", json={"target_date": "2026-11-02"}
    )
    assert copied.status_code == 200
    copy = client.get("/api/workouts/?date=2026-11-02").json()[0]
    assert (copy["duration_s"], copy["amount"], copy["amount_unit"]) == (
        1800,
        3,
        "miles",
    )


# --- the database, for the writer that skips Pydantic (ADR-0002) -------------


def test_the_unit_vocabulary_binds_the_raw_writer_too():
    conn = _raw()
    _seed_raw(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE workouts SET amount_unit = 'furlongs' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE exercises SET cardio_unit = 'furlongs' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE workouts SET duration_s = -1 WHERE id = 1")
    conn.close()


def test_cardio_edits_are_audited():
    """The triggers enumerate their columns, so new ones are invisible to the
    log until the triggers are rebuilt."""
    conn = _raw()
    _seed_raw(conn)
    conn.execute("UPDATE workouts SET duration_s = 1500, amount = 75 WHERE id = 1")
    conn.execute("UPDATE exercises SET cardio_unit = 'steps' WHERE id = 1")
    conn.commit()
    rows = conn.execute(
        "SELECT table_name, old_values, new_values FROM audit_log WHERE op = 'UPDATE'"
    ).fetchall()
    conn.close()

    by_table = {r["table_name"]: r for r in rows}
    workout_old = json.loads(by_table["workouts"]["old_values"])
    workout_new = json.loads(by_table["workouts"]["new_values"])
    assert (workout_old["duration_s"], workout_old["amount"]) == (1200, 60)
    assert (workout_new["duration_s"], workout_new["amount"]) == (1500, 75)
    assert workout_new["amount_unit"] == "floors"

    exercise_old = json.loads(by_table["exercises"]["old_values"])
    exercise_new = json.loads(by_table["exercises"]["new_values"])
    assert (exercise_old["cardio_unit"], exercise_new["cardio_unit"]) == (
        "floors",
        "steps",
    )
