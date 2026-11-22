import pytest

pytestmark = pytest.mark.usefixtures("db_engine")


def test_workouts_create_fetch_and_complete(client):
    payload = {
        "date": "2024-01-01",
        "exercise": "Bench",
        "category": "Push",
        "weight": 100,
        "reps": 5,
    }
    response = client.post("/api/workouts/", json=payload)
    assert response.status_code == 201
    workout = response.json()

    by_id = client.get(f"/api/workouts/{workout['doc_id']}")
    assert by_id.status_code == 200

    completed = client.patch(
        f"/api/workouts/{workout['doc_id']}/complete",
        json={"completed": True},
    )
    assert completed.status_code == 200
    assert completed.json()["completed_at"] is not None


def test_workouts_get_by_date_and_move(client):
    payload = {
        "date": "2024-01-02",
        "exercise": "Squat",
        "category": "Legs",
        "weight": 150,
        "reps": 5,
    }
    response = client.post("/api/workouts/", json=payload)
    assert response.status_code == 201

    by_date = client.get("/api/workouts/?date=2024-01-02")
    assert by_date.status_code == 200
    assert len(by_date.json()) == 1

    bad_move = client.post(
        "/api/workouts/date/2024-01-02/move",
        json={"target_date": "2024-01-02"},
    )
    assert bad_move.status_code == 400

    moved = client.post(
        "/api/workouts/date/2024-01-02/move",
        json={"target_date": "2024-01-03"},
    )
    assert moved.status_code == 200
    assert moved.json()["count"] == 1


def test_workouts_bulk_reorder_handles_empty(client):
    response = client.patch("/api/workouts/reorder", json={"workout_ids": []})
    assert response.status_code == 400


# --- Performance writes (plan 0018) ------------------------------------------


def _create_timed_tile(client, date="2024-04-01", **overrides):
    # The tile can only carry what the exercise offers (plan 0018): a fresh
    # Farmer Carry has Reps/Weight on and Time off, so it is configured here.
    client.post(
        "/api/exercises/",
        json={
            "name": "Farmer Carry",
            "category": "Legs",
            "time_enabled": True,
            "default_work_seconds": 40,
        },
    )
    payload = {
        "date": date,
        "exercise": "Farmer Carry",
        "category": "Legs",
        "reps": 2,
        "work_seconds": 40,
        "rest_seconds": 20,
        "rest_after_seconds": 15,
    }
    payload.update(overrides)
    response = client.post("/api/workouts/", json=payload)
    assert response.status_code == 201
    return response.json()


def test_targets_serialize_on_create_and_fetch(client):
    tile = _create_timed_tile(client)

    for field in ("work_seconds", "rest_seconds", "rest_after_seconds"):
        assert tile[field] is not None
    assert tile["work_seconds"] == 40
    assert tile["ended_early"] is False
    assert tile["completed_reps"] is None

    by_date = client.get("/api/workouts/?date=2024-04-01").json()
    assert by_date[0]["rest_after_seconds"] == 15


def test_perform_natural_completion_derives_actuals(client):
    tile = _create_timed_tile(client, date="2024-04-02")

    performed = client.post(f"/api/workouts/{tile['doc_id']}/perform", json={})
    assert performed.status_code == 200
    body = performed.json()
    assert body["completed_at"] is not None
    assert body["completed_reps"] == 2
    # Totals: 2 reps of 40s work, one 20s rest between them.
    assert body["actual_work_seconds"] == 80
    assert body["actual_rest_seconds"] == 20
    assert body["ended_early"] is False
    # Played tiles are logged on the day they are performed, not planned for.
    from app.utils.date_helpers import get_current_date

    assert body["date"] == get_current_date()


def test_perform_stopped_accepts_measured_actuals(client):
    tile = _create_timed_tile(client, date="2024-04-03")

    performed = client.post(
        f"/api/workouts/{tile['doc_id']}/perform",
        json={
            "ended_early": True,
            "completed_reps": 1,
            "actual_work_seconds": 52.5,
            "actual_rest_seconds": 20,
        },
    )
    assert performed.status_code == 200
    body = performed.json()
    assert body["ended_early"] is True
    assert body["completed_reps"] == 1
    assert body["actual_work_seconds"] == 52.5
    # The target survives: 2 planned, 1 done.
    assert body["reps"] == 2


def test_perform_missing_tile_is_a_404(client):
    assert client.post("/api/workouts/9999/perform", json={}).status_code == 404


def test_perform_natural_honours_the_snapshot_over_the_current_targets(client):
    """The player's snapshot is immutable (plan 0018): a tile edited mid-run
    is still written as it was when Play was pressed — the values sent — not
    as whatever the tile holds by the time the write lands."""
    tile = _create_timed_tile(client, date="2024-04-08")
    # The tile is edited after the run starts.
    client.put(
        f"/api/workouts/{tile['doc_id']}",
        json={
            "date": "2024-04-08",
            "exercise": "Farmer Carry",
            "category": "Legs",
            "reps": 9,
            "work_seconds": 99,
        },
    )

    performed = client.post(
        f"/api/workouts/{tile['doc_id']}/perform",
        json={"completed_reps": 2, "actual_work_seconds": 40, "actual_rest_seconds": 20},
    ).json()

    assert performed["ended_early"] is False
    assert performed["completed_reps"] == 2
    assert performed["actual_work_seconds"] == 40
    # The targets keep the edit — it is the record of what is planned now;
    # the actuals are what the run measured then.
    assert performed["reps"] == 9


def test_rest_after_records_a_partial_divider(client):
    tile = _create_timed_tile(client, date="2024-04-04")
    client.post(f"/api/workouts/{tile['doc_id']}/perform", json={})

    recorded = client.patch(
        f"/api/workouts/{tile['doc_id']}/rest-after",
        json={"actual_rest_after_seconds": 7.5},
    )
    assert recorded.status_code == 200
    assert recorded.json()["actual_rest_after_seconds"] == 7.5


def test_rest_after_refuses_a_planned_tile(client):
    tile = _create_timed_tile(client, date="2024-04-05")

    response = client.patch(
        f"/api/workouts/{tile['doc_id']}/rest-after",
        json={"actual_rest_after_seconds": 7.5},
    )
    assert response.status_code == 409


def test_rest_after_missing_tile_is_a_404(client):
    response = client.patch(
        "/api/workouts/9999/rest-after", json={"actual_rest_after_seconds": 7.5}
    )
    assert response.status_code == 404


def test_manual_tick_derives_actuals_without_a_timer(client):
    tile = _create_timed_tile(client, date="2024-04-06")

    completed = client.patch(
        f"/api/workouts/{tile['doc_id']}/complete", json={"completed": True}
    ).json()
    assert completed["completed_reps"] == 2
    assert completed["actual_work_seconds"] == 80
    # And the tile keeps the date the user logged it under — the move-to-today
    # rule is the player's, not the checkbox's.
    assert completed["date"] == "2024-04-06"


def test_editing_a_performed_tile_does_not_uncomplete_it(client):
    """A PUT carrying only a comment must not clear completion — the edit
    form is not a performance write, and adding feedback to a set after
    running it is precisely what happens to one."""
    tile = _create_timed_tile(client, date="2024-04-07")
    performed = client.post(f"/api/workouts/{tile['doc_id']}/perform", json={}).json()

    edited = client.put(
        f"/api/workouts/{tile['doc_id']}",
        json={
            "date": performed["date"],
            "exercise": "Farmer Carry",
            "category": "Legs",
            "reps": 2,
            "work_seconds": 40,
            "rest_seconds": 20,
            "rest_after_seconds": 15,
            "comment": "forearms gone by 30s",
        },
    ).json()

    assert edited["completed_at"] is not None
    assert edited["completed_reps"] == 2
    assert edited["comment"] == "forearms gone by 30s"


def test_perform_is_idempotent_over_http(client):
    """A retried write — the client's response was lost — returns the tile as
    it already is rather than completing it a second time."""
    tile = _create_timed_tile(client, date="2024-04-09")

    first = client.post(f"/api/workouts/{tile['doc_id']}/perform", json={})
    assert first.status_code == 200
    second = client.post(f"/api/workouts/{tile['doc_id']}/perform", json={})
    assert second.status_code == 200
    assert second.json()["completed_at"] == first.json()["completed_at"]
    assert second.json()["date"] == first.json()["date"]

    movement = client.get("/api/exercises/Farmer Carry").json()
    assert movement["use_count"] == 1


def test_a_comment_edit_preserves_legacy_time_and_the_new_fields(client):
    """`time` is read-only legacy, and the timing targets are sticky when an
    update omits them — an older client editing a comment must not wipe
    either."""
    created = client.post(
        "/api/workouts/",
        json={
            "date": "2024-04-10",
            "exercise": "Plank",
            "category": "Core",
            "time": "0:30",
        },
    ).json()
    # `time` is not writable at all any more, but the row still answers.
    assert created["time"] is None

    # Seed a legacy value directly, the way pre-0018 rows hold it.
    from app import database
    from app.db.models import Workout as WorkoutRow

    with database.SessionLocal() as session:
        row = session.get(WorkoutRow, created["doc_id"])
        row.time = "0:30"
        session.commit()

    plank = client.get("/api/exercises/Plank").json()
    client.put(f"/api/exercises/{plank['doc_id']}", json={"time_enabled": True})
    timed = client.post(
        "/api/workouts/",
        json={
            "date": "2024-04-10",
            "exercise": "Plank",
            "category": "Core",
            "work_seconds": 30,
        },
    ).json()
    assert timed["work_seconds"] == 30

    edited_legacy = client.put(
        f"/api/workouts/{created['doc_id']}",
        json={"date": "2024-04-10", "exercise": "Plank", "category": "Core",
              "comment": "held steady"},
    ).json()
    assert edited_legacy["time"] == "0:30"
    assert edited_legacy["comment"] == "held steady"

    edited_timed = client.put(
        f"/api/workouts/{timed['doc_id']}",
        json={"date": "2024-04-10", "exercise": "Plank", "category": "Core",
              "comment": "shaking by 25"},
    ).json()
    assert edited_timed["work_seconds"] == 30
    assert edited_timed["comment"] == "shaking by 25"


def _stopped_tile(client):
    tile = client.post(
        "/api/workouts/",
        json={"date": "2026-11-23", "exercise": "Plank", "category": "Core", "reps": 6},
    ).json()
    # Time on for Plank, then give the tile its timing.
    client.put("/api/exercises/" + str(client.get("/api/exercises/Plank").json()["doc_id"]),
               json={"time_enabled": True})
    client.put(f"/api/workouts/{tile['doc_id']}", json={
        "date": "2026-11-23", "exercise": "Plank", "category": "Core",
        "reps": 6, "work_seconds": 10, "rest_seconds": 5,
    })
    stopped = client.post(f"/api/workouts/{tile['doc_id']}/perform", json={
        "ended_early": True, "completed_reps": 3,
        "actual_work_seconds": 30, "actual_rest_seconds": 10,
    }).json()
    assert stopped["ended_early"] is True
    return stopped


def test_count_full_clears_ended_early_and_derives_the_targets(client):
    stopped = _stopped_tile(client)

    counted = client.post(f"/api/workouts/{stopped['doc_id']}/count-full")
    assert counted.status_code == 200
    body = counted.json()
    assert body["ended_early"] is False
    assert body["completed_at"] == stopped["completed_at"]
    assert (body["completed_reps"], body["actual_work_seconds"], body["actual_rest_seconds"]) == (6, 60, 25)


def test_reset_clears_a_stopped_set_back_to_planned(client):
    stopped = _stopped_tile(client)

    reset = client.patch(f"/api/workouts/{stopped['doc_id']}/complete", json={"completed": False}).json()
    assert reset["completed_at"] is None
    assert reset["ended_early"] is False
    assert reset["completed_reps"] is None


def test_count_full_needs_a_completed_set(client):
    tile = client.post(
        "/api/workouts/",
        json={"date": "2026-11-23", "exercise": "Plank", "category": "Core", "reps": 6},
    ).json()
    assert client.post(f"/api/workouts/{tile['doc_id']}/count-full").status_code == 409
    assert client.post("/api/workouts/99999/count-full").status_code == 404

