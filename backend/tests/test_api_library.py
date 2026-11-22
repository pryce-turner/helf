"""The library, saved programs, and blocks as script (plan 0022)."""

from app.services.library_service import preset_to_script


def _block(client, name, items):
    preset = client.post("/api/presets/", json={"name": name}).json()
    for item in items:
        client.post(f"/api/presets/{preset['doc_id']}/items", json=item)
    return client.get(f"/api/presets/{preset['doc_id']}").json()


def _enable_time(client, name, category="Core"):
    client.post("/api/exercises/", json={"name": name, "category": category, "time_enabled": True})


def test_a_block_reads_back_as_script_with_runs_folded(client):
    _enable_time(client, "Side Plank")
    block = _block(client, "Sides", [
        {"exercise": "Side Plank", "category": "Core", "reps": 1, "work_seconds": 30, "comment": "left"},
        {"exercise": "Side Plank", "category": "Core", "reps": 1, "work_seconds": 30, "comment": "right"},
        {"exercise": "Bird Dog", "category": "Core", "reps": 6, "weight": 2.5},
        {"exercise": "Bird Dog", "category": "Core", "reps": 6, "weight": 2.5},
        {"exercise": "Bird Dog", "category": "Core", "reps": 6, "weight": 2.5, "is_mobility": True},
    ])
    assert preset_to_script(block) == (
        'Side Plank / 1x1 30s "left"\n'
        'Side Plank / 1x1 30s "right"\n'
        "Bird Dog / 2x6 2.5lb\n"
        "Bird Dog / 1x6 2.5lb ~\n"
    )
    assert client.get(f"/api/presets/{block['doc_id']}/script").json()["script"].startswith("Side Plank")


def test_a_program_includes_your_block_by_name(client):
    _enable_time(client, "Plank")
    _block(client, "My core", [{"exercise": "Plank", "category": "Core", "reps": 3, "work_seconds": 20}])
    generated = client.post(
        "/api/upcoming/liftoscript/generate",
        json={"script": "## Day 1\n[My core]\nBarbell Squat / 1x5 135lb", "num_cycles": 1},
    )
    assert generated.status_code == 200, generated.text
    (session,) = client.get("/api/upcoming/").json()
    assert [(i["exercise"], i["work_seconds"]) for i in session["items"]] == [
        ("Plank", 20),
        ("Barbell Squat", None),
    ]


def test_check_validates_without_touching_the_queue(client):
    client.post(
        "/api/upcoming/liftoscript/generate",
        json={"script": "## Day 1\nBench Press / 3x5 135lb", "num_cycles": 1},
    )
    ok = client.post("/api/library/check", json={"script": "## A\n[Press warm-up]\n## B\nBench Press / 1x5 135lb"})
    assert ok.status_code == 200
    assert ok.json()["sessions"] == 2
    assert ok.json()["mobility_sets"] == ok.json()["sets"] - 1
    bad = client.post("/api/library/check", json={"script": "## A\n[Nope]"})
    assert bad.status_code == 400 and "no block named 'Nope'" in bad.json()["detail"]
    queue = client.get("/api/upcoming/").json()
    assert [i["exercise"] for s in queue for i in s["items"]] == ["Bench Press"] * 3


def test_the_library_lists_all_four_sources(client):
    _block(client, "Mine", [])
    client.post("/api/programs/", json={"name": "My program", "script": "## A\nPlank / 1x1"})
    library = client.get("/api/library/").json()
    blocks = {(b["source"], b["name"]) for b in library["blocks"]}
    programs = {(p["source"], p["name"]) for p in library["programs"]}
    assert ("mine", "Mine") in blocks and ("builtin", "Press core") in blocks
    assert ("mine", "My program") in programs and ("builtin", "5/3/1 Core Stability") in programs
    press_core = next(b for b in library["blocks"] if b["name"] == "Press core")
    assert press_core["set_count"] == 4


def test_duplicating_a_builtin_block_makes_an_editable_one(client):
    made = client.post("/api/library/blocks/builtin/squat_core/duplicate")
    assert made.status_code == 201
    block = made.json()
    assert block["name"] == "Squat core (mine)"
    assert [i["comment"] for i in block["items"][:4]] == [
        "Chop, left side", "Chop, right side", "Lift, left side", "Lift, right side",
    ]
    again = client.post("/api/library/blocks/builtin/squat_core/duplicate").json()
    assert again["name"] == "Squat core (mine) 2"


def test_builtin_block_names_are_reserved(client):
    assert client.post("/api/presets/", json={"name": "press core"}).status_code == 409
    pid = client.post("/api/presets/", json={"name": "Fine"}).json()["doc_id"]
    assert client.put(f"/api/presets/{pid}", json={"name": "Press Core"}).status_code == 409


def test_saved_programs_crud_and_builder_detach(client):
    builder = {"weeks": 1, "days": []}
    made = client.post("/api/programs/", json={"name": "P", "script": "## A\n", "builder": builder})
    assert made.status_code == 201
    pid = made.json()["doc_id"]
    assert made.json()["builder"] == builder
    assert client.post("/api/programs/", json={"name": "P"}).status_code == 409

    # Both sent: kept together.
    kept = client.put(f"/api/programs/{pid}", json={"script": "## B\n", "builder": builder}).json()
    assert kept["builder"] == builder
    # Script alone is a hand edit: the builder lets go.
    detached = client.put(f"/api/programs/{pid}", json={"script": "## C\n"}).json()
    assert (detached["script"], detached["builder"]) == ("## C\n", None)
    # A rename alone touches nothing else.
    renamed = client.put(f"/api/programs/{pid}", json={"name": "Q"}).json()
    assert (renamed["name"], renamed["script"]) == ("Q", "## C\n")

    assert client.delete(f"/api/programs/{pid}").status_code == 204
    assert client.get(f"/api/programs/{pid}").status_code == 404
