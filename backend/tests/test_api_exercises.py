import pytest

pytestmark = pytest.mark.usefixtures("db_engine")


def test_exercises_crud_and_categories(client):
    payload = {"name": "Bench", "category": "Push"}
    response = client.post("/api/exercises/", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Bench"

    by_name = client.get("/api/exercises/Bench")
    assert by_name.status_code == 200

    categories = client.get("/api/exercises/categories/")
    assert categories.status_code == 200
    assert categories.json()[0]["name"] == "Push"

    by_category = client.get("/api/exercises/categories/Push/exercises")
    assert by_category.status_code == 200
    assert by_category.json()["exercises"] == ["Bench"]


def test_exercise_not_found_returns_404(client):
    response = client.get("/api/exercises/Unknown")
    assert response.status_code == 404
