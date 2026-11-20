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
    assert body["actual_work_seconds"] == 40
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
    assert completed["actual_work_seconds"] == 40
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
