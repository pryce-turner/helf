EGG = {
    "name": "Egg",
    "kcal_per_serving": 78,
    "protein_g": 6.3,
    "carb_g": 0.6,
    "fat_g": 5.3,
}


def test_create_and_search_food(client):
    created = client.post("/api/food/", json=EGG)
    assert created.status_code == 201
    assert created.json()["brand"] == ""

    found = client.get("/api/food/", params={"q": "eg"})
    assert [f["name"] for f in found.json()] == ["Egg"]


def test_log_food_and_read_the_day(client):
    food_id = client.post("/api/food/", json=EGG).json()["doc_id"]

    logged = client.post(
        "/api/food/log",
        json={"food_id": food_id, "servings": 2, "consumed_at": "2026-08-07T08:00:00", "meal": "breakfast"},
    )
    assert logged.status_code == 201
    assert logged.json()["kcal"] == 156

    day = client.get("/api/food/log", params={"date": "2026-08-07"})
    assert day.status_code == 200
    assert len(day.json()) == 1
    assert day.json()[0]["meal"] == "breakfast"


def test_log_endpoint_is_not_shadowed_by_the_food_id_route(client):
    """`/api/food/log` must not be parsed as food_id="log"."""
    assert client.get("/api/food/log", params={"date": "2026-08-07"}).status_code == 200


def test_log_requires_a_food(client):
    assert client.post("/api/food/log", json={"servings": 1}).status_code == 422


def test_log_with_unknown_food_id_is_404_not_500(client):
    response = client.post("/api/food/log", json={"food_id": 9999, "servings": 1})
    assert response.status_code == 404


def test_log_rejects_an_unknown_meal(client):
    food_id = client.post("/api/food/", json=EGG).json()["doc_id"]
    response = client.post(
        "/api/food/log", json={"food_id": food_id, "servings": 1, "meal": "elevenses"}
    )
    assert response.status_code == 422


def test_summary_reports_partial_macros_with_a_gap_count(client):
    known = client.post("/api/food/", json=EGG).json()["doc_id"]
    unknown = client.post(
        "/api/food/", json={"name": "Leftovers", "kcal_per_serving": 400}
    ).json()["doc_id"]
    for food_id in (known, unknown):
        client.post(
            "/api/food/log",
            json={"food_id": food_id, "servings": 1, "consumed_at": "2026-08-07T12:00:00"},
        )

    summary = client.get(
        "/api/food/log/summary", params={"start": "2026-08-01", "end": "2026-08-31"}
    ).json()
    assert len(summary) == 1
    assert summary[0]["kcal"] == 478
    assert summary[0]["foods_missing_macros"] == 1


def test_update_food_is_404_for_an_unknown_id(client):
    assert client.put("/api/food/9999", json={"kcal_per_serving": 1}).status_code == 404


def test_delete_log_entry(client):
    food_id = client.post("/api/food/", json=EGG).json()["doc_id"]
    log_id = client.post(
        "/api/food/log",
        json={"food_id": food_id, "servings": 1, "consumed_at": "2026-08-07T08:00:00"},
    ).json()["doc_id"]

    assert client.delete(f"/api/food/log/{log_id}").status_code == 200
    assert client.delete(f"/api/food/log/{log_id}").status_code == 404


def test_day_endpoint_returns_totals_and_entries_together(client):
    food_id = client.post("/api/food/", json=EGG).json()["doc_id"]
    client.post(
        "/api/food/log",
        json={"food_id": food_id, "servings": 2, "consumed_at": "2026-08-07T08:00:00"},
    )

    day = client.get("/api/food/day", params={"date": "2026-08-07"}).json()
    assert day["totals"]["kcal"] == 156
    assert len(day["entries"]) == 1


def test_day_endpoint_answers_for_a_day_with_nothing_on_it(client):
    """The page needs the kcal target before anything is logged, which is
    exactly when it is most useful."""
    day = client.get("/api/food/day", params={"date": "2026-08-07"}).json()
    assert day["date"] == "2026-08-07"
    assert day["totals"]["kcal"] is None
    assert day["totals"]["kcal_target"] is None
    assert day["entries"] == []


MAGNESIUM = {"name": "Magnesium", "kind": "supplement", "serving_desc": "1 capsule"}


def _log(client, food_id, at, **extra):
    return client.post(
        "/api/food/log",
        json={"food_id": food_id, "consumed_at": at, **extra},
    ).json()


def test_the_food_day_is_meals_only(client):
    """Supplements share the table but not the page.

    They are logged with no meal and no calories, so on the food page they were
    a standing list of rows that never moved a total. The count moves with
    them: a day on which only supplements were swallowed is not a logged food
    day.
    """
    egg = client.post("/api/food/", json=EGG).json()["doc_id"]
    mag = client.post("/api/food/", json=MAGNESIUM).json()["doc_id"]
    _log(client, egg, "2026-08-07T08:00:00", meal="breakfast")
    _log(client, mag, "2026-08-07T07:00:00")

    day = client.get("/api/food/day", params={"date": "2026-08-07"}).json()
    assert [e["name"] for e in day["entries"]] == ["Egg"]
    assert day["totals"]["entries"] == 1
    # Still counted for adherence — it is only the food page that ignores them.
    assert day["totals"]["supplements_taken"] == 1


def test_a_day_of_supplements_alone_is_not_a_logged_food_day(client):
    mag = client.post("/api/food/", json=MAGNESIUM).json()["doc_id"]
    _log(client, mag, "2026-08-07T07:00:00")

    summary = client.get(
        "/api/food/log/summary", params={"start": "2026-08-01", "end": "2026-08-31"}
    ).json()
    assert summary == []


def test_recent_log_reads_across_days_newest_first(client):
    """The supplements page's log. Date-scoped reads cannot show a dose filed
    against the wrong day, which is the mistake worth being able to find."""
    mag = client.post("/api/food/", json=MAGNESIUM).json()["doc_id"]
    egg = client.post("/api/food/", json=EGG).json()["doc_id"]
    _log(client, mag, "2026-08-05T07:00:00")
    _log(client, mag, "2026-08-07T07:00:00")
    _log(client, egg, "2026-08-07T08:00:00", meal="breakfast")

    recent = client.get(
        "/api/food/log/recent", params={"kind": "supplement"}
    ).json()
    assert [e["consumed_at"] for e in recent] == [
        "2026-08-07T07:00:00",
        "2026-08-05T07:00:00",
    ]

    assert len(client.get("/api/food/log/recent").json()) == 3
    assert len(client.get("/api/food/log/recent", params={"limit": 1}).json()) == 1


def test_recent_log_is_not_shadowed_by_the_food_id_route(client):
    assert client.get("/api/food/log/recent").status_code == 200
