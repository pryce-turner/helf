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
