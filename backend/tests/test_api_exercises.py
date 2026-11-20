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
            "movement_break_enabled": True,
            "time_enabled": True,
            "default_work_seconds": 40,
        },
    )

    pool = client.get("/api/exercises/movement-breaks").json()
    assert [exercise["name"] for exercise in pool] == ["Deep Squat Hold"]
    assert pool[0]["movement_break_enabled"] is True
    assert pool[0]["default_work_seconds"] == 40
    assert pool[0]["form"] == "sink and stay"


def test_the_pool_route_is_not_eaten_by_the_lookup_by_name(client):
    """/movement-breaks would match `/{exercise_name}` if it were registered after it,
    and come back 404 rather than an empty pool."""
    assert client.get("/api/exercises/movement-breaks").status_code == 200
    assert client.get("/api/exercises/movement-breaks").json() == []


def test_leaving_a_movement_out_of_the_pool_is_not_the_same_as_removing_it(client):
    created = client.post(
        "/api/exercises/",
        json={
            "name": "Wall Angel",
            "category": "Shoulders",
            "movement_break_enabled": True,
        },
    ).json()
    assert created["movement_break_enabled"] is True

    # An edit to something else must not quietly unpool it.
    edited = client.put(
        f"/api/exercises/{created['doc_id']}", json={"form": "keep three contacts"}
    ).json()
    assert edited["movement_break_enabled"] is True

    removed = client.put(
        f"/api/exercises/{created['doc_id']}", json={"movement_break_enabled": False}
    ).json()
    assert removed["movement_break_enabled"] is False
    assert client.get("/api/exercises/movement-breaks").json() == []


def test_field_config_round_trips_over_http(client):
    """Farmer Carry is the shape the whole feature is for: Reps, Weight and
    Time on, the load filled in on the day rather than defaulted, and in the
    movement break pool."""
    created = client.post(
        "/api/exercises/",
        json={
            "name": "Farmer Carry",
            "category": "Legs",
            "reps_enabled": True,
            "weight_enabled": True,
            "default_weight_lb": None,
            "time_enabled": True,
            "default_work_seconds": 40,
            "default_rest_seconds": 20,
            "default_rest_after_seconds": 15,
            "movement_break_enabled": True,
        },
    )
    assert created.status_code == 201
    exercise = created.json()
    assert exercise["reps_enabled"] is True
    assert exercise["weight_enabled"] is True
    assert exercise["default_weight_lb"] is None
    assert exercise["time_enabled"] is True
    assert exercise["default_work_seconds"] == 40
    assert exercise["default_rest_seconds"] == 20
    assert exercise["default_rest_after_seconds"] == 15
    assert exercise["movement_break_enabled"] is True

    fetched = client.get("/api/exercises/Farmer Carry").json()
    assert fetched["default_work_seconds"] == 40
    assert fetched["movement_break_enabled"] is True


def test_a_disabled_group_keeps_its_defaults_for_reenabling(client):
    """Turning a group off is not a delete: the defaults stay stored, so
    turning it back on restores the configuration instead of a blank one."""
    created = client.post(
        "/api/exercises/",
        json={
            "name": "Sled Push",
            "category": "Legs",
            "time_enabled": True,
            "default_work_seconds": 30,
        },
    ).json()

    disabled = client.put(
        f"/api/exercises/{created['doc_id']}", json={"time_enabled": False}
    ).json()
    assert disabled["time_enabled"] is False
    assert disabled["default_work_seconds"] == 30

    reenabled = client.put(
        f"/api/exercises/{created['doc_id']}", json={"time_enabled": True}
    ).json()
    assert reenabled["time_enabled"] is True
    assert reenabled["default_work_seconds"] == 30


def test_field_defaults_are_bounded_for_the_http_writer(client):
    created = client.post(
        "/api/exercises/", json={"name": "Wall Sit", "category": "Legs"}
    ).json()

    for field, bad in (
        ("default_reps", 0),
        ("default_weight_lb", -1),
        ("default_work_seconds", 0),
        ("default_work_seconds", 3601),
        ("default_rest_seconds", -1),
        ("default_rest_after_seconds", 3601),
        ("default_distance", -0.5),
    ):
        response = client.put(
            f"/api/exercises/{created['doc_id']}", json={field: bad}
        )
        assert response.status_code == 422, f"{field}={bad} should be rejected"
