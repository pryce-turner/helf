"""The mobility loop, end to end through the API.

The interesting behaviour is not any one endpoint — it is that a mobility
session survives everything the lifting planner does, and that transferring one
leaves a day the agent can find again.
"""

import pytest
from sqlalchemy import text

from app import database
from app.models.upcoming import UpcomingWorkoutCreate
from app.repositories.mobility_repo import PLAN_KIND, SESSION_KIND, MobilityRepository
from app.repositories.upcoming_repo import (
    MOBILITY,
    MOBILITY_SESSION,
    UpcomingWorkoutRepository,
)

pytestmark = pytest.mark.usefixtures("db_engine")


def write_pending(rationale: str = "Pigeon leads, right side first.") -> None:
    """What `write_next_mobility_session` does, through the app's own layer."""
    repo = UpcomingWorkoutRepository()
    repo.create_bulk(
        [
            UpcomingWorkoutCreate(
                session=MOBILITY_SESSION,
                kind=MOBILITY,
                exercise="Hanging Knee Raise",
                category="Core",
                reps=10,
                comment="tuck the feet behind on extension",
            ),
            UpcomingWorkoutCreate(
                session=MOBILITY_SESSION,
                kind=MOBILITY,
                exercise="Hanging Knee Raise",
                category="Core",
                reps=10,
                comment="tuck the feet behind on extension",
            ),
            UpcomingWorkoutCreate(
                session=MOBILITY_SESSION,
                kind=MOBILITY,
                exercise="Weighted Pigeon Squat",
                category="Legs",
                reps=5,
                weight=30,
                comment="lead with the right",
            ),
        ]
    )
    MobilityRepository().replace_plan_note(rationale)


def test_pending_is_empty_before_anything_is_written(client):
    body = client.get("/api/mobility/pending").json()

    assert body["ready"] is False
    assert body["items"] == []
    assert body["last_session"] is None


def test_pending_returns_the_session_and_its_rationale(client):
    write_pending()

    body = client.get("/api/mobility/pending").json()

    assert body["ready"] is True
    assert len(body["items"]) == 3
    assert body["rationale"] == "Pigeon leads, right side first."
    # Insertion order is the prescribed order - the table has no `order`
    # column, so nothing else carries it.
    assert [item["exercise"] for item in body["items"]] == [
        "Hanging Knee Raise",
        "Hanging Knee Raise",
        "Weighted Pigeon Squat",
    ]


def test_a_rationale_without_items_is_not_reported_as_a_plan(client):
    """A leftover note would otherwise explain a session that is not there."""
    MobilityRepository().replace_plan_note("orphaned reasoning")

    body = client.get("/api/mobility/pending").json()

    assert body["ready"] is False
    assert body["rationale"] is None


def test_transfer_writes_sets_and_marks_the_day(client):
    write_pending()

    response = client.post("/api/mobility/transfer", json={"date": "2026-08-11"})
    assert response.status_code == 200
    assert response.json()["count"] == 3

    # The pending session is consumed, not copied.
    assert client.get("/api/mobility/pending").json()["ready"] is False

    logged = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()
    assert len(logged) == 3
    assert [w["order"] for w in logged] == [1, 2, 3]
    # The cue travels onto the set, where the user overwrites it with feedback.
    assert logged[0]["comment"] == "tuck the feet behind on extension"

    with database.SessionLocal() as session:
        kinds = session.execute(text("SELECT kind, date FROM note")).all()
    assert kinds == [(SESSION_KIND, "2026-08-11")]


def test_transfer_appends_after_work_already_logged_that_day(client):
    """A mobility session run alongside lifting is still one day's work."""
    client.post(
        "/api/workouts/",
        json={"date": "2026-08-11", "exercise": "Bench", "category": "Push", "reps": 5},
    )
    write_pending()

    client.post("/api/mobility/transfer", json={"date": "2026-08-11"})

    logged = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()
    assert [w["order"] for w in logged] == [1, 2, 3, 4]
    assert logged[0]["exercise"] == "Bench"


def test_transfer_without_a_pending_session_is_404(client):
    assert client.post("/api/mobility/transfer", json={"date": "2026-08-11"}).status_code == 404


def test_last_session_carries_the_comments_forward(client):
    write_pending()
    client.post("/api/mobility/transfer", json={"date": "2026-08-11"})

    logged = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()
    client.put(
        f"/api/workouts/{logged[2]['doc_id']}",
        json={
            "date": "2026-08-11",
            "exercise": "Weighted Pigeon Squat",
            "category": "Legs",
            "reps": 4,
            "comment": "right side failed at 4",
        },
    )

    body = client.get("/api/mobility/pending").json()

    assert body["ready"] is False
    assert body["last_session"]["date"] == "2026-08-11"
    assert body["last_session"]["rationale"] == "Pigeon leads, right side first."
    comments = [s["comment"] for s in body["last_session"]["sets"]]
    assert "right side failed at 4" in comments


def test_clearing_pending_discards_it(client):
    write_pending()

    assert client.delete("/api/mobility/pending").status_code == 204
    assert client.get("/api/mobility/pending").json()["ready"] is False
    assert client.delete("/api/mobility/pending").status_code == 404


# --------------------------------------------------------------------------
# Marking a day by hand, from the day view
# --------------------------------------------------------------------------
def log_a_set(client, date: str, exercise: str = "Weighted Pigeon Squat") -> None:
    client.post(
        "/api/workouts/",
        json={"date": date, "exercise": exercise, "category": "Legs", "reps": 5},
    )


def test_an_unmarked_day_says_so(client):
    body = client.get("/api/mobility/day/2026-08-11").json()

    assert body == {"date": "2026-08-11", "is_mobility": False, "rationale": None}


def test_marking_a_day_makes_it_the_session_the_agent_reads_back(client):
    """The whole point: a session run without the planner is otherwise invisible.

    `is_mobility` on the exercises cannot stand in for this - the pigeon squat
    is in the mobility pool, but so is every lifting day that happens to
    include one.
    """
    log_a_set(client, "2026-08-11")

    body = client.put(
        "/api/mobility/day/2026-08-11", json={"is_mobility": True}
    ).json()
    assert body["is_mobility"] is True
    # Nothing was prescribed, so nothing is claimed to have been.
    assert body["rationale"] is None

    last = client.get("/api/mobility/pending").json()["last_session"]
    assert last["date"] == "2026-08-11"
    assert [s["exercise"] for s in last["sets"]] == ["Weighted Pigeon Squat"]


def test_marking_twice_is_the_same_as_marking_once(client):
    log_a_set(client, "2026-08-11")

    client.put("/api/mobility/day/2026-08-11", json={"is_mobility": True})
    client.put("/api/mobility/day/2026-08-11", json={"is_mobility": True})

    with database.SessionLocal() as session:
        rows = session.execute(
            text("SELECT id FROM note WHERE kind = :k"), {"k": SESSION_KIND}
        ).all()
    assert len(rows) == 1


def test_marking_a_transferred_day_does_not_blank_the_agents_reasoning(client):
    """The marker and the rationale are one row, so a careless re-mark loses it."""
    write_pending()
    client.post("/api/mobility/transfer", json={"date": "2026-08-11"})

    client.put("/api/mobility/day/2026-08-11", json={"is_mobility": True})

    body = client.get("/api/mobility/day/2026-08-11").json()
    assert body["rationale"] == "Pigeon leads, right side first."


def test_marking_a_day_leaves_a_pending_session_alone(client):
    """Marking a day the user already logged says nothing about one still waiting."""
    log_a_set(client, "2026-08-11")
    write_pending()

    client.put("/api/mobility/day/2026-08-11", json={"is_mobility": True})

    assert client.get("/api/mobility/pending").json()["ready"] is True


def test_unmarking_removes_the_day_from_the_agents_view(client):
    log_a_set(client, "2026-08-09")
    log_a_set(client, "2026-08-11")
    client.put("/api/mobility/day/2026-08-09", json={"is_mobility": True})
    client.put("/api/mobility/day/2026-08-11", json={"is_mobility": True})

    body = client.put(
        "/api/mobility/day/2026-08-11", json={"is_mobility": False}
    ).json()
    assert body["is_mobility"] is False

    # The one before it becomes the session the next prescription is written
    # from, which is what unmarking a day mistakenly marked has to mean.
    assert client.get("/api/mobility/pending").json()["last_session"]["date"] == (
        "2026-08-09"
    )


def test_unmarking_a_day_that_was_never_marked_is_not_an_error(client):
    assert (
        client.put(
            "/api/mobility/day/2026-08-11", json={"is_mobility": False}
        ).status_code
        == 200
    )


def test_a_malformed_date_is_rejected_rather_than_stored(client):
    """It would become a marker dated to nonsense, sorting after every real day.

    `note.date` is computed from `substr(noted_at, 1, 10)`, so nothing
    downstream rejects it, and `ORDER BY noted_at DESC` would hand it to the
    agent as the last session performed - forever.
    """
    assert client.put(
        "/api/mobility/day/last-tuesday", json={"is_mobility": True}
    ).status_code == 422

    with database.SessionLocal() as session:
        assert session.execute(text("SELECT COUNT(*) FROM note")).scalar() == 0


def test_marking_does_not_disturb_the_days_sets(client):
    """The marker is a note. Nothing about the logged rows changes."""
    log_a_set(client, "2026-08-11")
    before = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()

    client.put("/api/mobility/day/2026-08-11", json={"is_mobility": True})

    assert client.get("/api/workouts/", params={"date": "2026-08-11"}).json() == before


# --------------------------------------------------------------------------
# The cost of sharing a table with the lifting planner
# --------------------------------------------------------------------------
def test_generating_a_lifting_program_leaves_mobility_alone(client):
    """The regression the single-table decision is one missing filter away from.

    `delete_all()` clears the board before a Liftoscript program is written.
    Unscoped, it would take the pending mobility session with it and the
    mobility tab would fall back to "no session ready" for a reason nothing on
    screen could explain.
    """
    write_pending()

    response = client.post(
        "/api/upcoming/liftoscript/generate",
        json={"script": "## Day 1\nBench Press / 3x5 135lb", "num_cycles": 1},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    assert client.get("/api/mobility/pending").json()["ready"] is True


def test_mobility_rows_do_not_appear_in_the_lifting_planner(client):
    write_pending()

    assert client.get("/api/upcoming/").json() == []


def test_lifting_rows_do_not_appear_on_the_mobility_tab(client):
    UpcomingWorkoutRepository().create(
        UpcomingWorkoutCreate(session=MOBILITY_SESSION, exercise="Bench", category="Push")
    )

    assert client.get("/api/mobility/pending").json()["ready"] is False


def test_plan_note_is_replaced_not_accumulated():
    """One rolling routine means one rationale; a stale one would be read as
    current by whichever query reached it first."""
    repo = MobilityRepository()
    repo.replace_plan_note("first")
    repo.replace_plan_note("second")

    with database.SessionLocal() as session:
        rows = session.execute(
            text("SELECT body FROM note WHERE kind = :k"), {"k": PLAN_KIND}
        ).all()

    assert rows == [("second",)]
