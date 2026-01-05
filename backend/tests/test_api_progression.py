import pytest

pytestmark = pytest.mark.usefixtures("db_engine")


def test_progression_exercise_list(client):
    client.post(
        "/api/exercises/",
        json={"name": "Bench", "category": "Push"},
    )

    response = client.get("/api/progression/exercises/list")
    assert response.status_code == 200
    assert response.json() == ["Bench"]


def test_progression_returns_historical_and_upcoming(client):
    client.post(
        "/api/workouts/",
        json={
            "date": "2024-01-01",
            "exercise": "Bench",
            "category": "Push",
            "weight": 100,
            "reps": 5,
        },
    )
    client.post(
        "/api/upcoming/",
        json={"session": 1, "exercise": "Bench", "category": "Push", "weight": 110, "reps": 3},
    )

    response = client.get("/api/progression/Bench")
    assert response.status_code == 200
    payload = response.json()
    assert payload["historical"]
    assert payload["upcoming"]


def test_progression_main_lifts_endpoint(client):
    response = client.get("/api/progression/")
    assert response.status_code == 200
    assert "Barbell Squat" in response.json()
