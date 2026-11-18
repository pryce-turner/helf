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


def test_rating_round_trips_over_http(client):
    created = client.post(
        "/api/exercises/", json={"name": "Hip Airplane", "category": "Legs"}
    ).json()
    assert created["rating"] is None
    # Mobility is a property of the set (d7e4f2a91b83), so the exercise
    # contract says nothing about it in either direction.
    assert "is_mobility" not in created

    rated = client.put(
        f"/api/exercises/{created['doc_id']}",
        json={"rating": 4},
    )
    assert rated.status_code == 200
    assert rated.json()["rating"] == 4
    assert "is_mobility" not in rated.json()


def test_explicit_null_rating_clears_it_over_http(client):
    """The repository distinguishes an omitted field from an explicit null via
    `model_fields_set`. That only works if FastAPI's parsing preserves it, so
    the guarantee is worth asserting through the HTTP layer and not just the
    repository."""
    created = client.post(
        "/api/exercises/",
        json={"name": "Jefferson Curl", "category": "Back", "rating": 3},
    ).json()
    assert created["rating"] == 3

    cleared = client.put(
        f"/api/exercises/{created['doc_id']}", json={"rating": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["rating"] is None

    # And an unrelated edit must not clear it.
    client.put(f"/api/exercises/{created['doc_id']}", json={"rating": 2})
    renamed = client.put(
        f"/api/exercises/{created['doc_id']}", json={"form": "slow eccentric"}
    )
    assert renamed.json()["rating"] == 2


def test_form_and_application_are_edited_independently(client):
    """The split exists so that recording what a session taught you cannot
    damage how the movement is performed (e2b9c4d17a05)."""
    created = client.post(
        "/api/exercises/",
        json={
            "name": "QL Raise",
            "category": "Core",
            "form": "hold the brace, ribs down",
            "application": "second set fades -> load too high -> drop 5lb",
        },
    ).json()
    assert created["form"] == "hold the brace, ribs down"

    updated = client.put(
        f"/api/exercises/{created['doc_id']}",
        json={"application": "left lags right -> asymmetry -> lead with the left"},
    ).json()

    assert updated["application"] == "left lags right -> asymmetry -> lead with the left"
    assert updated["form"] == "hold the brace, ribs down"


def test_rating_out_of_range_is_rejected(client):
    created = client.post(
        "/api/exercises/", json={"name": "Cossack Squat", "category": "Legs"}
    ).json()

    response = client.put(
        f"/api/exercises/{created['doc_id']}", json={"rating": 9}
    )
    assert response.status_code == 422


def test_the_movement_break_pool_is_only_the_movements_in_it(client):
    """A dedicated read, not a filter over the catalog: the shuffle is run from
    a phone in an office and the catalog carries every movement's full `form`
    and `application`."""
    client.post("/api/exercises/", json={"name": "Barbell Squat", "category": "Legs"})
    client.post(
        "/api/exercises/",
        json={
            "name": "Deep Squat Hold",
            "category": "Legs",
            "form": "sink and stay",
            "movement_break_seconds": 40,
        },
    )

    pool = client.get("/api/exercises/movement-breaks").json()
    assert [exercise["name"] for exercise in pool] == ["Deep Squat Hold"]
    assert pool[0]["movement_break_seconds"] == 40
    assert pool[0]["form"] == "sink and stay"


def test_the_pool_route_is_not_eaten_by_the_lookup_by_name(client):
    """/movement-breaks would match `/{exercise_name}` if it were registered after it,
    and come back 404 rather than an empty pool."""
    assert client.get("/api/exercises/movement-breaks").status_code == 200
    assert client.get("/api/exercises/movement-breaks").json() == []


def test_leaving_a_movement_out_of_the_pool_is_not_the_same_as_removing_it(client):
    created = client.post(
        "/api/exercises/",
        json={"name": "Wall Angel", "category": "Shoulders", "movement_break_seconds": 40},
    ).json()
    assert created["movement_break_seconds"] == 40

    # An edit to something else must not quietly unpool it.
    edited = client.put(
        f"/api/exercises/{created['doc_id']}", json={"form": "keep three contacts"}
    ).json()
    assert edited["movement_break_seconds"] == 40

    # An explicit null removes it, the way `rating` is cleared.
    removed = client.put(
        f"/api/exercises/{created['doc_id']}", json={"movement_break_seconds": None}
    ).json()
    assert removed["movement_break_seconds"] is None
    assert client.get("/api/exercises/movement-breaks").json() == []


def test_movement_break_seconds_is_bounded_for_the_http_writer(client):
    created = client.post(
        "/api/exercises/", json={"name": "Wall Sit", "category": "Legs"}
    ).json()

    assert (
        client.put(
            f"/api/exercises/{created['doc_id']}", json={"movement_break_seconds": 4}
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/exercises/{created['doc_id']}", json={"movement_break_seconds": 900}
        ).status_code
        == 422
    )
