"""The unified upcoming queue (9c4e7b21f806).

One list for both authors: Liftoscript-generated sessions and the agent's
mobility prescriptions group by session, the agent's carrying their label and
rationale. Transfer carries each row's `is_mobility` onto the logged set and
promotes a plan's rationale into the note the mobility loop reads back.
"""

import pytest
from sqlalchemy import text

from app import database
from app.repositories.mobility_repo import SESSION_KIND

pytestmark = pytest.mark.usefixtures("db_engine")


def write_agent_session(label: str = "Low back", **overrides) -> dict:
    """The body `POST /api/mobility/pending` takes, with sane defaults."""
    body = {
        "label": label,
        "rationale": "Pigeon leads, right side first.",
        "items": [
            {"exercise": "Weighted Pigeon Squat", "sets": 2, "reps": 5, "weight_lb": 30},
            {"exercise": "Hanging Knee Raise", "reps": 10},
        ],
    }
    body.update(overrides)
    return body


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
    assert transfer.json()["label"] is None

    missing = client.get("/api/upcoming/session/1")
    assert missing.status_code == 404

    workouts = client.get("/api/workouts/?date=2024-01-10")
    assert workouts.status_code == 200
    assert len(workouts.json()) == 1


def test_a_timed_upcoming_set_keeps_its_duration_on_transfer(client):
    """Legacy `time` on a planned set parses into `work_seconds` at transfer
    (plan 0018) — the duration moves onto the tile rather than dropping with
    the legacy column."""
    client.post(
        "/api/exercises/",
        json={"name": "Plank", "category": "Core", "time_enabled": True},
    )
    client.post(
        "/api/upcoming/",
        json={"session": 1, "exercise": "Plank", "category": "Core", "time": "0:01:00"},
    )

    transfer = client.post(
        "/api/upcoming/session/1/transfer", json={"date": "2024-01-10"}
    )
    assert transfer.status_code == 200

    (tile,) = client.get("/api/workouts/?date=2024-01-10").json()
    assert tile["work_seconds"] == 60
    assert tile["time"] is None


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


def test_wendler_maxes_endpoint(client):
    """Test that the wendler maxes endpoint returns current 1RM values."""
    maxes = client.get("/api/upcoming/wendler/maxes")
    assert maxes.status_code == 200

    data = maxes.json()
    # Should have squat, bench, deadlift keys (values may be null if no data)
    assert "squat" in data
    assert "bench" in data
    assert "deadlift" in data


# --------------------------------------------------------------------------
# The queue is one list now
# --------------------------------------------------------------------------
def test_the_queue_groups_both_kinds_of_author_by_session(client):
    """A Liftoscript session and an agent session list together; the agent's
    carries its label and rationale, the generated one has nothing to say."""
    client.post(
        "/api/upcoming/bulk",
        json={
            "workouts": [
                {"session": 1, "exercise": "Bench", "category": "Push", "reps": 5},
                {"session": 2, "exercise": "Squat", "category": "Legs", "reps": 5},
            ]
        },
    )
    client.post("/api/mobility/pending", json=write_agent_session())

    queue = client.get("/api/upcoming/").json()

    assert [s["session"] for s in queue] == [1, 2, 3]
    assert queue[0]["label"] is None
    assert queue[0]["rationale"] is None
    assert [i["exercise"] for i in queue[0]["items"]] == ["Bench"]
    agent = queue[2]
    assert agent["label"] == "Low back"
    assert agent["rationale"] == "Pigeon leads, right side first."
    assert agent["generated_at"] is not None
    assert [i["exercise"] for i in agent["items"]] == [
        "Weighted Pigeon Squat",
        "Weighted Pigeon Squat",
        "Hanging Knee Raise",
    ]


def test_items_carry_the_mobility_flag(client):
    """Every workout has a mobility element, and the prescription says which
    sets it is — the day-view checkbox starts from what lands."""
    client.post(
        "/api/upcoming/",
        json={"session": 1, "exercise": "Bench", "category": "Push"},
    )
    client.post("/api/mobility/pending", json=write_agent_session())

    queue = client.get("/api/upcoming/").json()

    assert [i["is_mobility"] for i in queue[0]["items"]] == [False]
    assert all(i["is_mobility"] for i in queue[1]["items"])


def test_a_plan_with_no_rows_is_not_a_session(client):
    """A leftover plan row is a heading with nothing under it — omitted, the
    same rule the old mobility page followed."""
    client.post("/api/mobility/pending", json=write_agent_session())
    with database.SessionLocal() as session:
        session.execute(text("DELETE FROM upcoming_workouts"))
        session.commit()

    assert client.get("/api/upcoming/").json() == []


# --------------------------------------------------------------------------
# Transfer, unified
# --------------------------------------------------------------------------
def test_transfer_carries_the_flag_and_promotes_the_rationale(client):
    """The old mobility transfer, now the only transfer: flagged rows land as
    flagged sets, and the plan's rationale becomes the note
    `read_latest_mobility_session` reports as why the session was written."""
    session = client.post("/api/mobility/pending", json=write_agent_session()).json()[
        "session"
    ]

    response = client.post(
        f"/api/upcoming/session/{session}/transfer", json={"date": "2026-08-11"}
    )

    assert response.status_code == 200
    assert response.json()["count"] == 3
    assert response.json()["label"] == "Low back"

    # The pending session is consumed, not copied.
    assert client.get(f"/api/upcoming/session/{session}").status_code == 404

    logged = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()
    assert [w["is_mobility"] for w in logged] == [True, True, True]
    assert [w["order"] for w in logged] == [1, 2, 3]

    with database.SessionLocal() as db:
        notes = db.execute(text("SELECT kind, date FROM note")).all()
    assert notes == [(SESSION_KIND, "2026-08-11")]


def test_a_mixed_session_transfers_each_rows_own_flag(client):
    """Every workout has a mobility element: a session can prescribe lifting
    sets alongside mobility work, and each row keeps its own answer."""
    client.post(
        "/api/upcoming/bulk",
        json={
            "workouts": [
                {"session": 1, "exercise": "Romanian Deadlift", "category": "Legs",
                 "reps": 8, "weight": 135},
                {"session": 1, "exercise": "Pigeon Squat", "category": "Legs",
                 "reps": 5, "is_mobility": True},
            ]
        },
    )

    client.post("/api/upcoming/session/1/transfer", json={"date": "2026-08-11"})

    logged = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()
    by_exercise = {w["exercise"]: w["is_mobility"] for w in logged}
    assert by_exercise == {"Romanian Deadlift": False, "Pigeon Squat": True}
    # And the mobility read-back finds exactly the mobility element.
    last = client.get("/api/mobility/last-session").json()
    assert [s["exercise"] for s in last["sets"]] == ["Pigeon Squat"]


def test_transfer_appends_after_work_already_logged_that_day(client):
    """A session run alongside lifting is still one day's work — rows stack
    under what is there rather than renumbering it."""
    client.post(
        "/api/workouts/",
        json={"date": "2026-08-11", "exercise": "Bench", "category": "Push", "reps": 5},
    )
    session = client.post("/api/mobility/pending", json=write_agent_session()).json()[
        "session"
    ]

    client.post(f"/api/upcoming/session/{session}/transfer", json={"date": "2026-08-11"})

    logged = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()
    assert [w["order"] for w in logged] == [1, 2, 3, 4]
    assert logged[0]["exercise"] == "Bench"


def test_transfer_without_a_session_is_404(client):
    assert client.post(
        "/api/upcoming/session/99/transfer", json={"date": "2026-08-11"}
    ).status_code == 404


def test_a_lifting_session_promotes_no_note(client):
    """Nothing prescribed it, so there is nothing to say about why."""
    client.post(
        "/api/upcoming/",
        json={"session": 1, "exercise": "Bench", "category": "Push"},
    )

    response = client.post("/api/upcoming/session/1/transfer", json={"date": "2026-08-11"})

    assert response.json()["label"] is None
    with database.SessionLocal() as db:
        assert db.execute(text("SELECT COUNT(*) FROM note")).scalar() == 0


# --------------------------------------------------------------------------
# Delete, unified: rows and plan go together
# --------------------------------------------------------------------------
def test_deleting_a_session_takes_its_plan_with_it(client):
    """A plan left behind would lend its label to whatever session is numbered
    the same later."""
    session = client.post("/api/mobility/pending", json=write_agent_session()).json()[
        "session"
    ]

    assert client.delete(f"/api/upcoming/session/{session}").status_code == 204
    assert client.get("/api/upcoming/").json() == []
    with database.SessionLocal() as db:
        assert db.execute(text("SELECT COUNT(*) FROM mobility_plan")).scalar() == 0


# --------------------------------------------------------------------------
# Generate clears the board — really clears it (9c4e7b21f806)
# --------------------------------------------------------------------------
def test_generating_a_program_replaces_the_whole_queue(client):
    """The kind-scoped delete used to spare the pending mobility session. The
    guard is the page's warning now, not a filter, so the agent's session and
    its plan go with everything else."""
    client.post("/api/mobility/pending", json=write_agent_session())
    client.post(
        "/api/upcoming/",
        json={"session": 9, "exercise": "Bench", "category": "Push"},
    )

    response = client.post(
        "/api/upcoming/liftoscript/generate",
        json={"script": "## Day 1\nBench Press / 3x5 135lb", "num_cycles": 1},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["deleted_count"] == 4

    queue = client.get("/api/upcoming/").json()
    assert [s["session"] for s in queue] == [1]
    assert all(i["exercise"] == "Bench Press" for s in queue for i in s["items"])
    with database.SessionLocal() as db:
        assert db.execute(text("SELECT COUNT(*) FROM mobility_plan")).scalar() == 0


def test_the_last_generated_program_is_kept_for_the_editor(client):
    """The editor reopens on the program behind the queue rather than an empty
    box: each successful generate keeps its script and cycle count."""
    assert client.get("/api/upcoming/liftoscript/last").json() is None

    first = "## Day 1\nBench Press / 3x5 135lb"
    second = "## Day 1\nBarbell Squat / 5x5 185lb"
    client.post("/api/upcoming/liftoscript/generate", json={"script": first, "num_cycles": 2})
    client.post("/api/upcoming/liftoscript/generate", json={"script": second, "num_cycles": 3})

    last = client.get("/api/upcoming/liftoscript/last").json()
    assert last["script"] == second
    assert last["num_cycles"] == 3
    assert last["generated_at"]


def test_a_program_that_fails_to_generate_is_not_kept(client):
    good = "## Day 1\nBench Press / 3x5 135lb"
    client.post("/api/upcoming/liftoscript/generate", json={"script": good, "num_cycles": 1})

    # Parses to nothing: no queue was produced, so it does not replace the
    # program the queue came from.
    client.post("/api/upcoming/liftoscript/generate", json={"script": "just words", "num_cycles": 1})

    assert client.get("/api/upcoming/liftoscript/last").json()["script"] == good


def test_scripted_timing_reaches_the_day(client):
    """Plan 0021 end to end: timing written in the script is queued, then
    lands on the day's set at transfer. A movement the script creates is
    configured to take it, or transfer's field-config guard would drop it."""
    generated = client.post(
        "/api/upcoming/liftoscript/generate",
        json={"script": "## Day 1\nBird Dog / 1x6 10s rest 5s after 30s\nSled / 1x1 40yd", "num_cycles": 1},
    )
    assert generated.status_code == 200, generated.text

    (session,) = client.get("/api/upcoming/").json()
    bird, sled = session["items"]
    assert (bird["work_seconds"], bird["rest_seconds"], bird["rest_after_seconds"]) == (10, 5, 30)
    assert (sled["distance"], sled["distance_unit"]) == (40, "yd")

    client.post("/api/upcoming/session/1/transfer", json={"date": "2026-11-23"})
    day = sorted(
        client.get("/api/workouts/", params={"date": "2026-11-23"}).json(),
        key=lambda w: w["order"],
    )
    assert (day[0]["work_seconds"], day[0]["rest_seconds"], day[0]["rest_after_seconds"]) == (10, 5, 30)
    assert (day[1]["distance"], day[1]["distance_unit"]) == (40, "yd")


def test_a_program_needing_a_group_an_exercise_has_off_is_refused(client):
    client.post("/api/exercises/", json={"name": "Plank", "category": "Core"})  # Time off
    client.post(
        "/api/upcoming/liftoscript/generate",
        json={"script": "## Day 1\nBench Press / 3x5 135lb", "num_cycles": 1},
    )

    refused = client.post(
        "/api/upcoming/liftoscript/generate",
        json={"script": "## Day 1\nPlank / 3x1 30s", "num_cycles": 1},
    )
    assert refused.status_code == 400
    assert "Plank has Time turned off" in refused.json()["detail"]
    # Refused before anything was cleared: the earlier queue is intact.
    queue = client.get("/api/upcoming/").json()
    assert [i["exercise"] for s in queue for i in s["items"]] == ["Bench Press"] * 3
    assert "Bench Press" in client.get("/api/upcoming/liftoscript/last").json()["script"]


def test_a_known_exercise_keeps_its_own_category(client):
    """The parser's built-in category list does not know most movements and
    says "Other"; a movement already in the catalog keeps its category."""
    client.post("/api/exercises/", json={"name": "Bird Dog", "category": "Core"})
    client.post(
        "/api/upcoming/liftoscript/generate",
        json={"script": "## Day 1\nBird Dog / 1x6\nBrand New Thing / 1x5", "num_cycles": 1},
    )
    (session,) = client.get("/api/upcoming/").json()
    assert [(i["exercise"], i["category"]) for i in session["items"]] == [
        ("Bird Dog", "Core"),
        ("Brand New Thing", "Other"),
    ]


def test_scripted_mobility_reaches_the_day(client):
    client.post(
        "/api/upcoming/liftoscript/generate",
        json={"script": "## Day 1\nPigeon Stretch / 1x2 60s ~\nBarbell Squat / 1x5 135lb", "num_cycles": 1},
    )
    (session,) = client.get("/api/upcoming/").json()
    assert [i["is_mobility"] for i in session["items"]] == [True, False]

    client.post("/api/upcoming/session/1/transfer", json={"date": "2026-11-23"})
    day = sorted(
        client.get("/api/workouts/", params={"date": "2026-11-23"}).json(),
        key=lambda w: w["order"],
    )
    assert [(w["exercise"], w["is_mobility"]) for w in day] == [
        ("Pigeon Stretch", True),
        ("Barbell Squat", False),
    ]
