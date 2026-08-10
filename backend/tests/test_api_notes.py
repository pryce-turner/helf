def test_create_note_generates_date_and_defaults_source(client):
    created = client.post(
        "/api/notes/",
        json={"body": "left knee tweaked on set 3", "kind": "injury", "noted_at": "2026-08-07T19:00:00"},
    )
    assert created.status_code == 201
    assert created.json()["date"] == "2026-08-07"
    assert created.json()["source"] == "manual"


def test_notes_filter_by_kind_and_range(client):
    for kind, noted_at in [
        ("intention", "2026-08-01T08:00:00"),
        ("review", "2026-08-05T20:00:00"),
        ("intention", "2026-08-09T08:00:00"),
    ]:
        client.post("/api/notes/", json={"body": kind, "kind": kind, "noted_at": noted_at})

    intentions = client.get("/api/notes/", params={"kind": "intention"}).json()
    assert len(intentions) == 2
    # Most recent first.
    assert intentions[0]["date"] == "2026-08-09"

    ranged = client.get(
        "/api/notes/", params={"start": "2026-08-02", "end": "2026-08-06"}
    ).json()
    assert [n["kind"] for n in ranged] == ["review"]


def test_agent_written_notes_are_distinguishable(client):
    """The reason `source` exists: once the agent can write notes, "did I
    observe this or did a model infer it?" is otherwise unanswerable."""
    client.post("/api/notes/", json={"body": "inferred a deload week", "source": "agent"})
    assert client.get("/api/notes/").json()[0]["source"] == "agent"


def test_note_kinds_summarises_notes_and_documents(client):
    client.post("/api/notes/", json={"body": "a", "kind": "review", "noted_at": "2026-08-01T08:00:00"})
    client.post("/api/notes/", json={"body": "b", "kind": "review", "noted_at": "2026-08-03T08:00:00"})
    client.post("/api/notes/", json={"body": "c", "noted_at": "2026-08-04T08:00:00"})

    kinds = {row["kind"]: row for row in client.get("/api/notes/kinds").json()}
    assert kinds["review"]["count"] == 2
    assert kinds["review"]["first"] == "2026-08-01"
    assert kinds["review"]["last"] == "2026-08-03"
    # A note with no kind is still counted, under an explicit label rather
    # than vanishing into a NULL group.
    assert kinds["(none)"]["count"] == 1


def test_kinds_route_is_not_shadowed_by_the_note_id_route(client):
    assert client.get("/api/notes/kinds").status_code == 200


def test_delete_note(client):
    note_id = client.post("/api/notes/", json={"body": "typo"}).json()["doc_id"]
    assert client.delete(f"/api/notes/{note_id}").status_code == 200
    assert client.delete(f"/api/notes/{note_id}").status_code == 404


def test_empty_body_is_rejected(client):
    assert client.post("/api/notes/", json={"body": ""}).status_code == 422
