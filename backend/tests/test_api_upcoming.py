import pytest

pytestmark = pytest.mark.usefixtures("db_engine")


def test_upcoming_create_and_session_transfer(client):
    response = client.post(
        "/api/upcoming/",
        json={"session": 1, "exercise": "Bench", "category": "Push"},
    )
    assert response.status_code == 201

    transfer = client.post(
        "/api/upcoming/session/1/transfer",
        json={"date": "2024-01-10"},
    )
    assert transfer.status_code == 200
    assert transfer.json()["count"] == 1

    missing = client.get("/api/upcoming/session/1")
    assert missing.status_code == 404

    workouts = client.get("/api/workouts/?date=2024-01-10")
    assert workouts.status_code == 200
    assert len(workouts.json()) == 1


def test_upcoming_bulk_create_and_delete(client):
    response = client.post(
        "/api/upcoming/bulk",
        json={
            "workouts": [
                {"session": 2, "exercise": "Squat", "category": "Legs"},
                {"session": 2, "exercise": "Lunge", "category": "Legs"},
            ]
        },
    )
    assert response.status_code == 201

    deleted = client.delete("/api/upcoming/session/2")
    assert deleted.status_code == 204


def test_wendler_generate_and_maxes(client):
    maxes = client.get("/api/upcoming/wendler/maxes")
    assert maxes.status_code == 200

    generated = client.post(
        "/api/upcoming/wendler/generate",
        json={"num_cycles": 1, "squat_max": 200, "bench_max": 150, "deadlift_max": 250},
    )
    assert generated.status_code == 200
    assert generated.json()["count"] == 72
