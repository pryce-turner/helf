"""Workout presets: hand-built workouts, applied to a day as planned sets (plan 0020)."""

SQUAT = {"exercise": "Barbell Squat", "category": "Legs", "weight": 185, "reps": 5}
PLANK = {"exercise": "Plank", "category": "Core", "reps": 1, "is_mobility": True}


def _preset(client, name=None):
    created = client.post("/api/presets/", json={"name": name} if name else None)
    assert created.status_code == 201, created.text
    return created.json()


def test_an_unnamed_preset_gets_a_numbered_default(client):
    assert _preset(client)["name"] == "New preset"
    assert _preset(client)["name"] == "New preset 2"
    assert _preset(client)["name"] == "New preset 3"


def test_names_are_unique_and_never_blank(client):
    _preset(client, "Leg day")
    assert client.post("/api/presets/", json={"name": "Leg day"}).status_code == 409
    assert client.post("/api/presets/", json={"name": "   "}).status_code == 422

    other = _preset(client, "Push")
    assert client.put(f"/api/presets/{other['doc_id']}", json={"name": "Leg day"}).status_code == 409
    renamed = client.put(f"/api/presets/{other['doc_id']}", json={"name": "  Push A  "})
    assert renamed.json()["name"] == "Push A"


def test_tiles_append_in_order_and_read_back_as_targets(client):
    preset = _preset(client, "Leg day")
    pid = preset["doc_id"]
    first = client.post(f"/api/presets/{pid}/items", json=SQUAT).json()
    second = client.post(f"/api/presets/{pid}/items", json=PLANK).json()
    assert (first["order"], second["order"]) == (1, 2)

    read = client.get(f"/api/presets/{pid}").json()
    assert [i["exercise"] for i in read["items"]] == ["Barbell Squat", "Plank"]
    assert read["items"][0]["weight"] == 185
    assert read["items"][1]["is_mobility"] is True
    # A preset tile has targets only: there is nothing to perform.
    assert "completed_at" not in read["items"][0]


def test_a_disabled_group_cannot_be_filled(client):
    """The day's field-config guard applies to preset tiles too: a fresh
    exercise has Time disabled, so timing sent for it is dropped."""
    pid = _preset(client)["doc_id"]
    item = client.post(
        f"/api/presets/{pid}/items", json={**SQUAT, "work_seconds": 30}
    ).json()
    assert item["work_seconds"] is None
    assert item["reps"] == 5


def test_edit_reorder_and_delete_tiles(client):
    pid = _preset(client)["doc_id"]
    a = client.post(f"/api/presets/{pid}/items", json=SQUAT).json()
    b = client.post(f"/api/presets/{pid}/items", json=PLANK).json()

    edited = client.put(f"/api/presets/items/{a['doc_id']}", json={**SQUAT, "reps": 3})
    assert edited.json()["reps"] == 3

    assert client.patch(
        f"/api/presets/{pid}/reorder", json={"item_ids": [b["doc_id"], a["doc_id"]]}
    ).status_code == 200
    order = [i["exercise"] for i in client.get(f"/api/presets/{pid}").json()["items"]]
    assert order == ["Plank", "Barbell Squat"]

    assert client.delete(f"/api/presets/items/{b['doc_id']}").status_code == 204
    assert len(client.get(f"/api/presets/{pid}").json()["items"]) == 1


def test_reorder_ignores_another_presets_tiles(client):
    mine = _preset(client, "Mine")["doc_id"]
    theirs = _preset(client, "Theirs")["doc_id"]
    their_tile = client.post(f"/api/presets/{theirs}/items", json=SQUAT).json()
    client.post(f"/api/presets/{theirs}/items", json=PLANK)

    client.patch(f"/api/presets/{mine}/reorder", json={"item_ids": [their_tile["doc_id"]]})
    assert client.get(f"/api/presets/{theirs}").json()["items"][0]["order"] == 1


def test_apply_appends_planned_sets_after_the_days_own(client):
    client.post(
        "/api/workouts/",
        json={"date": "2026-11-23", "exercise": "Deadlift", "category": "Back", "reps": 5},
    )
    pid = _preset(client, "Leg day")["doc_id"]
    client.post(f"/api/presets/{pid}/items", json=SQUAT)
    client.post(f"/api/presets/{pid}/items", json=PLANK)

    applied = client.post(f"/api/presets/{pid}/apply", json={"date": "2026-11-23"})
    assert applied.status_code == 201
    assert applied.json()["count"] == 2

    day = sorted(
        client.get("/api/workouts/", params={"date": "2026-11-23"}).json(),
        key=lambda w: w["order"],
    )
    assert [w["exercise"] for w in day] == ["Deadlift", "Barbell Squat", "Plank"]
    # Planned, not performed — and the mobility flag travels with the tile.
    assert all(w["completed_at"] is None for w in day)
    assert day[2]["is_mobility"] is True
    assert day[1]["weight"] == 185


def test_editing_a_preset_after_applying_leaves_the_day_alone(client):
    pid = _preset(client)["doc_id"]
    tile = client.post(f"/api/presets/{pid}/items", json=SQUAT).json()
    client.post(f"/api/presets/{pid}/apply", json={"date": "2026-11-23"})

    client.put(f"/api/presets/items/{tile['doc_id']}", json={**SQUAT, "weight": 225})
    client.delete(f"/api/presets/{pid}")

    day = client.get("/api/workouts/", params={"date": "2026-11-23"}).json()
    assert [w["weight"] for w in day] == [185]


def test_applying_an_empty_preset_says_so(client):
    pid = _preset(client)["doc_id"]
    assert client.post(f"/api/presets/{pid}/apply", json={"date": "2026-11-23"}).status_code == 422


def test_missing_presets_are_404s(client):
    assert client.get("/api/presets/999").status_code == 404
    assert client.post("/api/presets/999/items", json=SQUAT).status_code == 404
    assert client.post("/api/presets/999/apply", json={"date": "2026-11-23"}).status_code == 404
    assert client.put("/api/presets/items/999", json=SQUAT).status_code == 404
    assert client.delete("/api/presets/999").status_code == 404


def test_apply_rejects_a_malformed_date(client):
    pid = _preset(client)["doc_id"]
    client.post(f"/api/presets/{pid}/items", json=SQUAT)
    assert client.post(f"/api/presets/{pid}/apply", json={"date": "23/11/2026"}).status_code == 422


def test_deleting_a_preset_takes_its_tiles(client, db_session):
    from sqlalchemy import text

    pid = _preset(client)["doc_id"]
    client.post(f"/api/presets/{pid}/items", json=SQUAT)
    assert client.delete(f"/api/presets/{pid}").status_code == 204
    left = db_session.execute(text("SELECT COUNT(*) FROM workout_preset_item")).scalar_one()
    assert left == 0
