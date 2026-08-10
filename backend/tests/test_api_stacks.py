"""Stacks: preset groups of consumables, logged in one action."""

OMEGA = {"name": "Omega-3", "kind": "supplement", "serving_desc": "1 softgel, 1000mg EPA"}
VIT_D = {"name": "Vitamin D3", "kind": "supplement", "serving_desc": "1 tablet, 5000 IU"}
CHOLESTOFF = {"name": "CholestOff", "brand": "Nature Made", "kind": "supplement"}
WHEY = {"name": "Whey Isolate", "kind": "supplement", "kcal_per_serving": 120,
        "protein_g": 25, "carb_g": 2, "fat_g": 1}


def _morning(client):
    return client.post(
        "/api/stacks/",
        json={
            "name": "Morning",
            "items": [
                {"food": OMEGA, "servings": 2},
                {"food": VIT_D, "servings": 1},
                {"food": CHOLESTOFF, "servings": 2},
            ],
        },
    )


def test_create_a_stack_creates_the_supplements_it_names(client):
    created = _morning(client)
    assert created.status_code == 201

    body = created.json()
    assert [i["name"] for i in body["items"]] == ["Omega-3", "Vitamin D3", "CholestOff"]
    assert body["items"][0]["servings"] == 2
    assert body["taken_today"] is False

    catalog = client.get("/api/food/", params={"kind": "supplement"}).json()
    assert len(catalog) == 3


def test_logging_a_stack_writes_one_entry_per_item(client):
    stack_id = _morning(client).json()["doc_id"]

    logged = client.post(
        f"/api/stacks/{stack_id}/log", json={"consumed_at": "2026-08-09T07:00:00"}
    )
    assert logged.status_code == 201
    assert len(logged.json()["entries"]) == 3

    day = client.get("/api/food/day", params={"date": "2026-08-09"}).json()
    assert len(day["entries"]) == 3
    assert day["totals"]["supplements_taken"] == 3


def test_supplements_do_not_trigger_the_missing_macros_warning(client):
    """The trap this feature would otherwise create. `foods_missing_macros`
    counts logged foods with an unknown macro, and a vitamin has none — without
    the `kind` filter every dose would report the day as understated, forever."""
    stack_id = _morning(client).json()["doc_id"]
    client.post(f"/api/stacks/{stack_id}/log", json={"consumed_at": "2026-08-09T07:00:00"})

    totals = client.get("/api/food/day", params={"date": "2026-08-09"}).json()["totals"]
    assert totals["foods_missing_macros"] == 0
    # And a genuinely under-described *meal* still is counted.
    client.post(
        "/api/food/log",
        json={"food": {"name": "Leftovers"}, "servings": 1,
              "consumed_at": "2026-08-09T13:00:00"},
    )
    totals = client.get("/api/food/day", params={"date": "2026-08-09"}).json()["totals"]
    assert totals["foods_missing_macros"] == 1


def test_a_supplement_with_real_macros_still_counts_as_intake(client):
    """Whey is food by any definition. Storing supplements in `food` is what
    keeps 120 kcal a scoop out of a blind spot."""
    stack_id = client.post(
        "/api/stacks/",
        json={"name": "Post-workout", "items": [{"food": WHEY, "servings": 2}]},
    ).json()["doc_id"]
    client.post(f"/api/stacks/{stack_id}/log", json={"consumed_at": "2026-08-09T17:00:00"})

    totals = client.get("/api/food/day", params={"date": "2026-08-09"}).json()["totals"]
    assert totals["kcal"] == 240
    assert totals["protein_g"] == 50


def test_taken_today_is_derived_from_the_log_not_from_the_button(client):
    """So it is true whether the stack was tapped or the items entered by hand,
    and so that editing a stack cannot rewrite what a past day claims."""
    stack_id = _morning(client).json()["doc_id"]
    items = client.get(f"/api/stacks/{stack_id}").json()["items"]

    # Log every item individually, never touching the stack endpoint.
    for item in items:
        client.post("/api/food/log", json={"food_id": item["food_id"], "servings": 1})

    assert client.get(f"/api/stacks/{stack_id}").json()["taken_today"] is True


def test_taken_today_is_false_until_every_item_is_logged(client):
    stack_id = _morning(client).json()["doc_id"]
    items = client.get(f"/api/stacks/{stack_id}").json()["items"]

    client.post("/api/food/log", json={"food_id": items[0]["food_id"], "servings": 1})
    assert client.get(f"/api/stacks/{stack_id}").json()["taken_today"] is False


def test_an_empty_stack_is_not_taken(client):
    """`MIN()` over no rows is NULL, and a vacuous true would report an empty
    stack as done every day."""
    stack_id = client.post("/api/stacks/", json={"name": "Empty"}).json()["doc_id"]
    assert client.get(f"/api/stacks/{stack_id}").json()["taken_today"] is False


def test_logging_an_empty_stack_is_refused(client):
    stack_id = client.post("/api/stacks/", json={"name": "Empty"}).json()["doc_id"]
    assert client.post(f"/api/stacks/{stack_id}/log").status_code == 422


def test_a_food_can_belong_to_two_stacks_with_different_servings(client):
    """Two omega capsules in the morning, one in the evening."""
    morning = _morning(client).json()
    omega_id = next(i["food_id"] for i in morning["items"] if i["name"] == "Omega-3")

    evening = client.post(
        "/api/stacks/",
        json={
            "name": "Evening",
            "items": [
                {"food": {"name": "Magnesium", "kind": "supplement"}, "servings": 1},
                {"food_id": omega_id, "servings": 1},
            ],
        },
    ).json()

    assert next(i for i in evening["items"] if i["food_id"] == omega_id)["servings"] == 1
    assert next(i for i in morning["items"] if i["food_id"] == omega_id)["servings"] == 2
    assert client.get("/api/food/", params={"kind": "supplement"}).json().__len__() == 4


def test_the_same_food_twice_in_one_stack_is_refused(client):
    """It would silently double the dose on every log."""
    response = client.post(
        "/api/stacks/",
        json={"name": "Doubled", "items": [{"food": OMEGA}, {"food": OMEGA}]},
    )
    assert response.status_code == 422
    assert "twice" in response.json()["detail"]


def test_updating_items_replaces_the_membership(client):
    stack_id = _morning(client).json()["doc_id"]

    updated = client.put(
        f"/api/stacks/{stack_id}",
        json={"items": [{"food": VIT_D, "servings": 1}]},
    ).json()

    assert [i["name"] for i in updated["items"]] == ["Vitamin D3"]


def test_editing_a_stack_does_not_change_what_a_past_day_recorded(client):
    """The reason `food_log` carries no `stack_id`."""
    stack_id = _morning(client).json()["doc_id"]
    client.post(f"/api/stacks/{stack_id}/log", json={"consumed_at": "2026-08-09T07:00:00"})

    client.put(f"/api/stacks/{stack_id}", json={"items": [{"food": VIT_D}]})

    day = client.get("/api/food/day", params={"date": "2026-08-09"}).json()
    assert len(day["entries"]) == 3


def test_deleting_a_stack_keeps_the_foods_and_the_history(client):
    stack_id = _morning(client).json()["doc_id"]
    client.post(f"/api/stacks/{stack_id}/log", json={"consumed_at": "2026-08-09T07:00:00"})

    assert client.delete(f"/api/stacks/{stack_id}").status_code == 200
    assert client.get(f"/api/stacks/{stack_id}").status_code == 404

    assert len(client.get("/api/food/", params={"kind": "supplement"}).json()) == 3
    day = client.get("/api/food/day", params={"date": "2026-08-09"}).json()
    assert len(day["entries"]) == 3


def test_food_search_separates_supplements_from_meals(client):
    """A shared prefix is common — "ma" reaches both Mango and Magnesium — so
    each page filters to its own kind rather than offering the other's rows."""
    client.post("/api/food/", json={"name": "Mango", "kcal_per_serving": 60})
    client.post("/api/food/", json={"name": "Magnesium", "kind": "supplement"})

    meals = client.get("/api/food/", params={"q": "ma", "kind": "food"}).json()
    supplements = client.get("/api/food/", params={"q": "ma", "kind": "supplement"}).json()

    assert [f["name"] for f in meals] == ["Mango"]
    assert [f["name"] for f in supplements] == ["Magnesium"]


def test_an_unknown_kind_is_rejected(client):
    assert client.post("/api/food/", json={"name": "X", "kind": "vitamin"}).status_code == 422


def test_stack_referencing_a_missing_food_is_422(client):
    response = client.post(
        "/api/stacks/", json={"name": "Bad", "items": [{"food_id": 9999}]}
    )
    assert response.status_code == 422


def test_log_of_an_unknown_stack_is_404(client):
    assert client.post("/api/stacks/9999/log").status_code == 404


# --------------------------------------------------------------------------
# Editing a supplement — the catalog entry, not the group
# --------------------------------------------------------------------------
def test_usage_reports_what_an_edit_would_rewrite(client):
    """Editing macros is retroactive, so the size of the blast radius has to be
    available *before* the edit, not discoverable after it."""
    stack_id = _morning(client).json()["doc_id"]
    omega = next(
        i for i in client.get(f"/api/stacks/{stack_id}").json()["items"]
        if i["name"] == "Omega-3"
    )["food_id"]

    client.post("/api/stacks/", json={"name": "Evening", "items": [{"food_id": omega}]})
    for day in ("2026-08-03", "2026-08-07", "2026-08-09"):
        client.post(
            "/api/food/log",
            json={"food_id": omega, "servings": 1, "consumed_at": f"{day}T07:00:00"},
        )

    usage = client.get(f"/api/food/{omega}/usage").json()
    assert usage["entries"] == 3
    assert usage["first_logged"] == "2026-08-03"
    assert usage["last_logged"] == "2026-08-09"
    # Named, so you can see what you are about to change.
    assert usage["stacks"] == ["Morning", "Evening"]


def test_usage_of_an_untouched_supplement_is_empty_not_missing(client):
    food_id = client.post(
        "/api/food/", json={"name": "Zinc", "kind": "supplement"}
    ).json()["doc_id"]

    usage = client.get(f"/api/food/{food_id}/usage").json()
    assert usage == {
        "food_id": food_id,
        "entries": 0,
        "first_logged": None,
        "last_logged": None,
        "stacks": [],
    }


def test_usage_of_an_unknown_food_is_404(client):
    assert client.get("/api/food/9999/usage").status_code == 404


def test_editing_a_supplement_rewrites_past_totals(client):
    """The whole reason the editor has to warn. Whey's calories are derived, so
    correcting them corrects history — which is right, and surprising."""
    stack_id = client.post(
        "/api/stacks/",
        json={"name": "Post-workout", "items": [{"food": WHEY, "servings": 2}]},
    ).json()["doc_id"]
    client.post(f"/api/stacks/{stack_id}/log", json={"consumed_at": "2026-08-07T17:00:00"})

    before = client.get("/api/food/day", params={"date": "2026-08-07"}).json()
    assert before["totals"]["kcal"] == 240

    whey = before["entries"][0]["food_id"]
    edited = client.put(f"/api/food/{whey}", json={"kcal_per_serving": 130})
    assert edited.status_code == 200

    after = client.get("/api/food/day", params={"date": "2026-08-07"}).json()
    assert after["totals"]["kcal"] == 260


def test_editing_serving_text_leaves_the_stack_membership_alone(client):
    """`serving_desc` is a property of the food; `servings` is a property of the
    membership. Correcting one must not disturb the other."""
    stack_id = _morning(client).json()["doc_id"]
    omega = next(
        i for i in client.get(f"/api/stacks/{stack_id}").json()["items"]
        if i["name"] == "Omega-3"
    )

    client.put(
        f"/api/food/{omega['food_id']}",
        json={"serving_desc": "1 softgel, 1200mg EPA"},
    )

    after = next(
        i for i in client.get(f"/api/stacks/{stack_id}").json()["items"]
        if i["food_id"] == omega["food_id"]
    )
    assert after["serving_desc"] == "1 softgel, 1200mg EPA"
    assert after["servings"] == 2


def test_a_supplement_cannot_be_renamed_onto_another(client):
    """UNIQUE (name, brand) — and the API should say so rather than 500."""
    _morning(client)
    zinc = client.post(
        "/api/food/", json={"name": "Zinc", "kind": "supplement"}
    ).json()["doc_id"]

    response = client.put(f"/api/food/{zinc}", json={"name": "Omega-3"})
    assert response.status_code == 409
