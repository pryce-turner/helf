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
from app.utils.date_helpers import get_current_date
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


# --------------------------------------------------------------------------
# Writing a session over HTTP - POST /pending, the twin of the MCP tool
# --------------------------------------------------------------------------
def session_body(label: str = "Low back", **overrides) -> dict:
    body = {
        "label": label,
        "rationale": "Dead bug leads. Hip to the box on the pigeon, not past it.",
        "items": [
            {"exercise": "Dead Bug", "sets": 2, "reps": 15, "weight_lb": 25},
            {"exercise": "Weighted Pigeon Stretch", "reps": 8, "weight_lb": 35},
        ],
    }
    body.update(overrides)
    return body


def pending_rows() -> int:
    with database.SessionLocal() as session:
        return session.execute(
            text("SELECT COUNT(*) FROM upcoming_workouts WHERE kind = 'mobility'")
        ).scalar()


def test_writing_a_new_label_creates_a_session(client):
    response = client.post("/api/mobility/pending", json=session_body())

    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "Low back"
    assert body["sets_written"] == 3
    assert body["movements"] == 2
    assert body["replaced_pending_rows"] == 0
    assert body["exercises_created"] == ["Dead Bug", "Weighted Pigeon Stretch"]

    plans = MobilityRepository().get_plans()
    assert [(p["session"], p["label"]) for p in plans] == [(body["session"], "Low back")]


def test_writing_a_label_again_replaces_only_that_session(client):
    shoulder = write_pending("Lock 3 daily", label="Shoulder")
    first = client.post("/api/mobility/pending", json=session_body()).json()

    second = client.post(
        "/api/mobility/pending",
        json=session_body(
            rationale="revised",
            items=[{"exercise": "Hip Thrust", "reps": 20, "weight_lb": 80}],
        ),
    ).json()

    assert second["session"] == first["session"]
    assert second["replaced_pending_rows"] == 3
    body = client.get("/api/mobility/pending").json()
    by_label = {s["label"]: s for s in body["sessions"]}
    assert [i["exercise"] for i in by_label["Low back"]["items"]] == ["Hip Thrust"]
    assert by_label["Low back"]["rationale"] == "revised"
    # The other label is untouched: same session number, same three rows.
    assert by_label["Shoulder"]["session"] == shoulder
    assert len(by_label["Shoulder"]["items"]) == 3


def test_sets_expand_into_one_row_per_set(client):
    client.post(
        "/api/mobility/pending",
        json=session_body(
            items=[
                {"exercise": "Dead Bug", "reps": 20, "weight_lb": 25},
                {"exercise": "Dead Bug", "sets": 2, "reps": 15, "weight_lb": 25},
            ]
        ),
    )

    items = client.get("/api/mobility/pending").json()["sessions"][0]["items"]
    assert [(i["exercise"], i["reps"], i["weight"]) for i in items] == [
        ("Dead Bug", 20, 25.0),
        ("Dead Bug", 15, 25.0),
        ("Dead Bug", 15, 25.0),
    ]
    assert all(i["comment"] is None for i in items)


def test_a_per_set_comment_is_rejected_and_nothing_is_written(client):
    body = session_body()
    body["items"][0]["comment"] = "slow on the way down"

    response = client.post("/api/mobility/pending", json=body)

    assert response.status_code == 422
    assert "feedback channel" in response.text
    assert pending_rows() == 0
    assert MobilityRepository().get_plans() == []


def test_weight_instead_of_weight_lb_is_rejected(client):
    body = session_body(items=[{"exercise": "Dead Bug", "reps": 20, "weight": 25}])

    response = client.post("/api/mobility/pending", json=body)

    assert response.status_code == 422
    assert pending_rows() == 0


@pytest.mark.parametrize(
    "overrides",
    [{"label": "  "}, {"rationale": ""}, {"items": []}],
    ids=["blank-label", "blank-rationale", "no-items"],
)
def test_an_incomplete_session_is_rejected(client, overrides):
    response = client.post("/api/mobility/pending", json=session_body(**overrides))

    assert response.status_code == 422
    assert pending_rows() == 0


def test_exercise_names_match_case_insensitively(client):
    log_a_set(client, "2026-08-11", "Dead Bug")

    body = client.post(
        "/api/mobility/pending",
        json=session_body(
            items=[{"exercise": "dead bug", "reps": 20, "category": "Mobility"}]
        ),
    ).json()

    assert body["exercises_created"] == []
    items = client.get("/api/mobility/pending").json()["sessions"][0]["items"]
    # The existing movement, under its own name and its own category.
    assert (items[0]["exercise"], items[0]["category"]) == ("Dead Bug", "Legs")


def test_a_new_exercise_lands_in_its_category_or_uncategorized(client):
    client.post(
        "/api/mobility/pending",
        json=session_body(
            items=[
                {"exercise": "Copenhagen Plank", "reps": 10, "category": "Core"},
                {"exercise": "Couch Stretch", "reps": 1},
            ]
        ),
    )

    items = client.get("/api/mobility/pending").json()["sessions"][0]["items"]
    assert [(i["exercise"], i["category"]) for i in items] == [
        ("Copenhagen Plank", "Core"),
        ("Couch Stretch", "Uncategorized"),
    ]


def test_a_written_session_shows_as_pending_and_transfers(client):
    session_id = client.post("/api/mobility/pending", json=session_body()).json()[
        "session"
    ]

    pending = client.get("/api/mobility/pending").json()
    assert pending["ready"] is True
    assert pending["sessions"][0]["session"] == session_id

    response = client.post(
        "/api/mobility/transfer", json={"date": "2026-09-25", "session": session_id}
    )
    assert response.status_code == 200
    assert response.json()["count"] == 3

    logged = client.get("/api/workouts/", params={"date": "2026-09-25"}).json()
    assert [w["exercise"] for w in logged] == [
        "Dead Bug",
        "Dead Bug",
        "Weighted Pigeon Stretch",
    ]
    assert all(w["is_mobility"] and w["comment"] is None for w in logged)
    last = client.get("/api/mobility/pending").json()["last_session"]
    assert last["rationale"].startswith("Dead bug leads.")


def audit_actors(table: str) -> set[str]:
    with database.SessionLocal() as session:
        return set(
            session.execute(
                text("SELECT DISTINCT actor FROM audit_log WHERE table_name = :t"),
                {"t": table},
            ).scalars()
        )


def current_actor() -> str:
    with database.SessionLocal() as session:
        return session.execute(text("SELECT actor FROM audit_actor")).scalar()


def test_a_written_session_is_audited_as_the_agent(client):
    """Only the agent writes sessions, so the audit log must say so - the same
    attribution the MCP tool gives the same rows.

    Of what a write touches, only `exercises` is audited (the planned rows and
    the plan are not), so a movement created by the write is what shows it.
    """
    client.post("/api/mobility/pending", json=session_body())

    assert audit_actors("exercises") == {"agent"}
    # Released inside the transaction, so the PWA's next write is its own.
    assert current_actor() == "app"


def test_a_failed_write_rolls_the_agent_claim_back(client):
    """A write that dies after claiming the actor must not leave every later
    change attributed to the agent."""
    with pytest.raises(KeyError):
        MobilityRepository().write_session("Low back", "why", [{"reps": 5}])

    assert current_actor() == "app"
    assert MobilityRepository().get_plans() == []


# --- Movement break ----------------------------------------------------------------

def test_a_finished_movement_break_run_is_logged_as_mobility_sets(client):
    client.post(
        "/api/exercises/",
        json={"name": "Deep Squat Hold", "category": "Legs", "movement_break_seconds": 40},
    )
    # Something already on the day, so "appended" is distinguishable from
    # "interleaved" — two snacks in one afternoon have to stack in the order
    # they were run, not sort themselves among the lifting.
    client.post(
        "/api/workouts/",
        json={
            "date": "2026-11-12",
            "exercise": "Barbell Squat",
            "category": "Legs",
            "weight": 225,
            "reps": 5,
        },
    )

    response = client.post(
        "/api/mobility/movement-break",
        json={
            "exercise": "Deep Squat Hold",
            "sets": 2,
            "seconds": 40,
            "date": "2026-11-12",
        },
    )
    assert response.status_code == 200
    assert response.json()["sets"] == 2
    assert response.json()["time"] == "0:40"

    day = client.get("/api/workouts/?date=2026-11-12").json()
    squat = next(w for w in day if w["exercise"] == "Barbell Squat")
    breaks = [w for w in day if w["exercise"] == "Deep Squat Hold"]

    assert len(breaks) == 2
    assert all(w["is_mobility"] for w in breaks)
    # A timed hold is not a rep, and writing `reps = 1` for one would put a rep
    # in the progression series that never happened (ADR-0005).
    assert all(w["reps"] is None for w in breaks)
    assert all(w["time"] == "0:40" for w in breaks)
    # It was run, which is the only reason the row exists.
    assert all(w["completed_at"] for w in breaks)
    assert [w["order"] for w in breaks] == [squat["order"] + 1, squat["order"] + 2]


def test_the_run_is_logged_as_it_was_run_not_as_it_was_suggested(client):
    """The times are adjustable after a shuffle, so the log takes the timer's
    setting rather than the movement's default bout."""
    client.post(
        "/api/exercises/",
        json={"name": "Wall Sit", "category": "Legs", "movement_break_seconds": 40},
    )

    client.post(
        "/api/mobility/movement-break",
        json={"exercise": "Wall Sit", "sets": 3, "seconds": 20, "date": "2026-11-12"},
    )

    day = client.get("/api/workouts/?date=2026-11-12").json()
    assert [w["time"] for w in day] == ["0:20", "0:20", "0:20"]


def test_a_run_of_an_unknown_movement_is_a_404_not_a_silent_no_op(client):
    response = client.post(
        "/api/mobility/movement-break",
        json={"exercise": "Nothing Like This", "sets": 2, "seconds": 30},
    )
    assert response.status_code == 404
    assert client.get("/api/workouts/?date=2026-11-12").json() == []


def test_a_movement_break_run_carries_no_comment(client):
    """The set's comment is the user's only feedback channel (0012 §4). A run
    that finished has nothing to say about itself."""
    client.post(
        "/api/exercises/", json={"name": "Chin Tuck", "category": "Back"}
    )

    client.post(
        "/api/mobility/movement-break",
        json={"exercise": "Chin Tuck", "sets": 1, "seconds": 30, "date": "2026-11-12"},
    )

    day = client.get("/api/workouts/?date=2026-11-12").json()
    assert day[0]["comment"] is None


def test_a_movement_break_run_defaults_to_today(client):
    client.post("/api/exercises/", json={"name": "Plank", "category": "Core"})

    response = client.post(
        "/api/mobility/movement-break", json={"exercise": "Plank", "sets": 1, "seconds": 30}
    )
    assert response.status_code == 200
    # The app's timezone, never the client's guess at a date.
    assert response.json()["date"] == get_current_date()
