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


def test_editing_a_comment_does_not_unflag_the_set(client):
    """The feedback edit is the one that must not cost the flag.

    `WorkoutUpdate.is_mobility` defaults to False and every other field on that
    model is a full replace, so a PUT carrying only a comment would clear it -
    and adding feedback to a set after running it is the whole read-back
    channel. The flag would vanish exactly when the loop needs it.
    """
    write_pending()
    client.post("/api/mobility/transfer", json={"date": "2026-08-11"})
    logged = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()

    client.put(
        f"/api/workouts/{logged[0]['doc_id']}",
        json={
            "date": "2026-08-11",
            "exercise": logged[0]["exercise"],
            "category": "Core",
            "reps": 10,
            "comment": "felt easy today",
        },
    )

    assert client.get("/api/mobility/pending").json()["last_session"] is not None
    still = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()
    assert still[0]["is_mobility"] is True


def test_unflagging_a_set_is_possible_when_actually_asked_for(client):
    write_pending()
    client.post("/api/mobility/transfer", json={"date": "2026-08-11"})
    logged = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()

    for row in logged:
        client.put(
            f"/api/workouts/{row['doc_id']}",
            json={
                "date": "2026-08-11",
                "exercise": row["exercise"],
                "category": "Core",
                "reps": row["reps"],
                "is_mobility": False,
            },
        )

    # No mobility set anywhere means no last session, not an empty one.
    assert client.get("/api/mobility/pending").json()["last_session"] is None


def test_clearing_pending_discards_it(client):
    write_pending()

    assert client.delete("/api/mobility/pending").status_code == 204
    assert client.get("/api/mobility/pending").json()["ready"] is False
    assert client.delete("/api/mobility/pending").status_code == 404


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
