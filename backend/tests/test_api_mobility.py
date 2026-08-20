"""The mobility loop, end to end through the API.

The interesting behaviour is not any one endpoint — it is that a mobility
session survives everything the lifting planner does, and that transferring one
leaves a day the agent can find again.
"""

import pytest
from sqlalchemy import text

from app import database
from app.models.upcoming import UpcomingWorkoutCreate
from app.repositories.mobility_repo import SESSION_KIND, MobilityRepository
from app.repositories.upcoming_repo import (
    MOBILITY,
    MOBILITY_SESSION,
    UpcomingWorkoutRepository,
)

pytestmark = pytest.mark.usefixtures("db_engine")


def write_pending(
    rationale: str = "Pigeon leads, right side first.",
    label: str = "Mobility",
) -> int:
    """What `write_next_mobility_session` does, through the app's own layer.

    Returns the session number, which callers need to transfer or discard it —
    several can be pending now, so nothing is addressable by "the" session.
    """
    plan = MobilityRepository().upsert_plan(label, rationale)
    session_id = plan["session"]
    repo = UpcomingWorkoutRepository()
    repo.create_bulk(
        [
            UpcomingWorkoutCreate(
                session=session_id,
                kind=MOBILITY,
                exercise="Hanging Knee Raise",
                category="Core",
                reps=10,
                comment="tuck the feet behind on extension",
            ),
            UpcomingWorkoutCreate(
                session=session_id,
                kind=MOBILITY,
                exercise="Hanging Knee Raise",
                category="Core",
                reps=10,
                comment="tuck the feet behind on extension",
            ),
            UpcomingWorkoutCreate(
                session=session_id,
                kind=MOBILITY,
                exercise="Weighted Pigeon Squat",
                category="Legs",
                reps=5,
                weight=30,
                comment="lead with the right",
            ),
        ]
    )
    return session_id


def test_pending_is_empty_before_anything_is_written(client):
    body = client.get("/api/mobility/pending").json()

    assert body["ready"] is False
    assert body["sessions"] == []
    assert body["last_session"] is None


def test_pending_returns_the_session_and_its_rationale(client):
    write_pending()

    body = client.get("/api/mobility/pending").json()

    assert body["ready"] is True
    assert len(body["sessions"][0]["items"]) == 3
    assert body["sessions"][0]["rationale"] == "Pigeon leads, right side first."
    # Insertion order is the prescribed order - the table has no `order`
    # column, so nothing else carries it.
    assert [item["exercise"] for item in body["sessions"][0]["items"]] == [
        "Hanging Knee Raise",
        "Hanging Knee Raise",
        "Weighted Pigeon Squat",
    ]


def test_a_rationale_without_items_is_not_reported_as_a_plan(client):
    """A leftover note would otherwise explain a session that is not there."""
    MobilityRepository().upsert_plan("Mobility", "orphaned reasoning")

    body = client.get("/api/mobility/pending").json()

    assert body["ready"] is False
    # A plan row with no items is a heading with nothing under it.
    assert body["sessions"] == []


def test_transfer_writes_sets_and_marks_the_day(client):
    session_id = write_pending()

    response = client.post("/api/mobility/transfer", json={"date": "2026-08-11", "session": session_id})
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
    session_id = write_pending()

    client.post("/api/mobility/transfer", json={"date": "2026-08-11", "session": session_id})

    logged = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()
    assert [w["order"] for w in logged] == [1, 2, 3, 4]
    assert logged[0]["exercise"] == "Bench"


def test_transfer_without_a_pending_session_is_404(client):
    assert client.post(
        "/api/mobility/transfer", json={"date": "2026-08-11", "session": 1}
    ).status_code == 404


def test_last_session_carries_the_comments_forward(client):
    session_id = write_pending()
    client.post("/api/mobility/transfer", json={"date": "2026-08-11", "session": session_id})

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
    session_id = write_pending()
    client.post("/api/mobility/transfer", json={"date": "2026-08-11", "session": session_id})
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
    session_id = write_pending()
    client.post("/api/mobility/transfer", json={"date": "2026-08-11", "session": session_id})
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
    session_id = write_pending()

    assert client.delete(f"/api/mobility/pending/{session_id}").status_code == 204
    assert client.get("/api/mobility/pending").json()["ready"] is False
    assert client.delete(f"/api/mobility/pending/{session_id}").status_code == 404


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


def test_a_label_holds_one_plan_row_not_a_pile(client):
    """The rationale is superseded per label, never appended to.

    It describes the session that is pending under that name, and only one is.
    """
    repo = MobilityRepository()
    repo.upsert_plan("Mobility", "first")
    repo.upsert_plan("Mobility", "second")

    plans = repo.get_plans()
    assert [(p["label"], p["rationale"]) for p in plans] == [("Mobility", "second")]


def test_two_labels_are_two_independent_sessions(client):
    """Rehabbing a low back and a shoulder at once is the whole feature."""
    low = write_pending("QL first", label="Low back")
    shoulder = write_pending("Lock 3 daily", label="Shoulder")
    assert low != shoulder

    body = client.get("/api/mobility/pending").json()
    assert [s["label"] for s in body["sessions"]] == ["Low back", "Shoulder"]

    # Transferring one leaves the other pending.
    client.post(
        "/api/mobility/transfer", json={"date": "2026-08-11", "session": low}
    )
    after = client.get("/api/mobility/pending").json()
    assert [s["label"] for s in after["sessions"]] == ["Shoulder"]


def test_discarding_one_session_leaves_the_other(client):
    write_pending("QL first", label="Low back")
    shoulder = write_pending("Lock 3 daily", label="Shoulder")

    assert client.delete(f"/api/mobility/pending/{shoulder}").status_code == 204

    body = client.get("/api/mobility/pending").json()
    assert [s["label"] for s in body["sessions"]] == ["Low back"]


# --------------------------------------------------------------------------
# Flagging a whole day at once
# --------------------------------------------------------------------------
def log_a_set(client, date: str, exercise: str = "Weighted Pigeon Squat") -> None:
    client.post(
        "/api/workouts/",
        json={"date": date, "exercise": exercise, "category": "Legs", "reps": 5},
    )


def test_marking_a_whole_day_flags_every_set(client):
    log_a_set(client, "2026-08-11", "Hanging Knee Raise")
    log_a_set(client, "2026-08-11", "Weighted Pigeon Squat")

    body = client.patch(
        "/api/workouts/date/2026-08-11/mobility", json={"is_mobility": True}
    ).json()

    assert (body["changed"], body["total"]) == (2, 2)
    assert client.get("/api/mobility/pending").json()["last_session"]["date"] == (
        "2026-08-11"
    )


def test_marking_a_day_twice_writes_nothing_the_second_time(client):
    """Every UPDATE fires an audit trigger, and `audit_log` cannot be tidied.

    A bulk button is the easy way to fill it with rows whose old and new values
    are identical, so the repository skips rows already holding the value.
    """
    log_a_set(client, "2026-08-11")
    client.patch("/api/workouts/date/2026-08-11/mobility", json={"is_mobility": True})

    second = client.patch(
        "/api/workouts/date/2026-08-11/mobility", json={"is_mobility": True}
    ).json()

    assert (second["changed"], second["total"]) == (0, 1)
    with database.SessionLocal() as session:
        writes = session.execute(
            text("SELECT COUNT(*) FROM audit_log WHERE table_name = 'workouts'")
        ).scalar()
    assert writes == 1


def test_unmarking_a_whole_day_clears_every_set(client):
    log_a_set(client, "2026-08-11", "Hanging Knee Raise")
    log_a_set(client, "2026-08-11", "Weighted Pigeon Squat")
    client.patch("/api/workouts/date/2026-08-11/mobility", json={"is_mobility": True})

    body = client.patch(
        "/api/workouts/date/2026-08-11/mobility", json={"is_mobility": False}
    ).json()

    assert body["changed"] == 2
    assert client.get("/api/mobility/pending").json()["last_session"] is None


def test_marking_a_day_leaves_other_days_alone(client):
    log_a_set(client, "2026-08-09")
    log_a_set(client, "2026-08-11")

    client.patch("/api/workouts/date/2026-08-11/mobility", json={"is_mobility": True})

    other = client.get("/api/workouts/", params={"date": "2026-08-09"}).json()
    assert [w["is_mobility"] for w in other] == [False]


def test_marking_a_day_with_nothing_logged_is_a_404(client):
    """Not a silent success. There is no day-level row to create (0013 §6), so
    a day with no sets is a day this cannot say anything about."""
    assert client.patch(
        "/api/workouts/date/2026-08-11/mobility", json={"is_mobility": True}
    ).status_code == 404


def test_marking_a_mixed_day_only_writes_the_sets_that_differ(client):
    log_a_set(client, "2026-08-11", "Hanging Knee Raise")
    log_a_set(client, "2026-08-11", "Weighted Pigeon Squat")
    first = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()[0]
    client.put(
        f"/api/workouts/{first['doc_id']}",
        json={
            "date": "2026-08-11",
            "exercise": first["exercise"],
            "category": "Legs",
            "reps": 5,
            "is_mobility": True,
        },
    )

    body = client.patch(
        "/api/workouts/date/2026-08-11/mobility", json={"is_mobility": True}
    ).json()

    assert (body["changed"], body["total"]) == (1, 2)


def test_a_hand_flagged_day_reads_back_without_a_rationale(client):
    """Regression: `rationale` was non-optional and 500'd the endpoint.

    Since the flag moved to the set, a session the user assembled by hand is
    the ordinary case, and nothing prescribed it — so there is no note and
    never will be. The page has to render that, not fail on it.
    """
    log_a_set(client, "2026-08-11")
    client.patch("/api/workouts/date/2026-08-11/mobility", json={"is_mobility": True})

    response = client.get("/api/mobility/pending")

    assert response.status_code == 200
    assert response.json()["last_session"]["rationale"] is None
