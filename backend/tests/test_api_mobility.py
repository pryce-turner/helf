"""The mobility loop, end to end through the API.

The queue half of mobility is the upcoming queue now (9c4e7b21f806) — listing,
transferring and discarding a pending session are covered in
`test_api_upcoming.py`. What is pinned here is what is genuinely mobility's:
the read-back the next prescription is written from, the day flagging that
feeds it, the agent's write path, and the movement-break shuffle.
"""

import pytest
from sqlalchemy import text

from app import database
from app.models.upcoming import UpcomingWorkoutCreate
from app.repositories.mobility_repo import MobilityRepository
from app.utils.date_helpers import get_current_date
from app.repositories.upcoming_repo import UpcomingWorkoutRepository

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
                is_mobility=True,
                exercise="Hanging Knee Raise",
                category="Core",
                reps=10,
            ),
            UpcomingWorkoutCreate(
                session=session_id,
                is_mobility=True,
                exercise="Hanging Knee Raise",
                category="Core",
                reps=10,
            ),
            UpcomingWorkoutCreate(
                session=session_id,
                is_mobility=True,
                exercise="Weighted Pigeon Squat",
                category="Legs",
                reps=5,
                weight=30,
            ),
        ]
    )
    return session_id


def test_last_session_is_none_before_anything_is_flagged(client):
    assert client.get("/api/mobility/last-session").json() is None


def test_last_session_carries_the_comments_forward(client):
    session_id = write_pending()
    client.post(f"/api/upcoming/session/{session_id}/transfer", json={"date": "2026-08-11"})

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

    body = client.get("/api/mobility/last-session").json()

    assert body["date"] == "2026-08-11"
    assert body["rationale"] == "Pigeon leads, right side first."
    comments = [s["comment"] for s in body["sets"]]
    assert "right side failed at 4" in comments


def test_last_session_carries_targets_and_actuals(client):
    """The next prescription is written from what was done, not only what was
    planned — so the read-back carries both, target beside actual (0018)."""
    client.post(
        "/api/exercises/",
        json={
            "name": "Farmer Carry",
            "category": "Legs",
            "time_enabled": True,
            "movement_break_enabled": True,
        },
    )
    tile = client.post(
        "/api/workouts/",
        json={
            "date": "2026-08-11",
            "exercise": "Farmer Carry",
            "category": "Legs",
            "reps": 2,
            "work_seconds": 40,
            "rest_seconds": 20,
            "rest_after_seconds": 15,
            "is_mobility": True,
        },
    ).json()
    # Stopped one rep in, with a partial second bout measured.
    client.post(
        f"/api/workouts/{tile['doc_id']}/perform",
        json={
            "ended_early": True,
            "completed_reps": 1,
            "actual_work_seconds": 52.5,
            "actual_rest_seconds": 20,
        },
    )

    last = client.get("/api/mobility/last-session").json()
    (performed,) = last["sets"]
    # Targets beside what was actually done.
    assert performed["reps"] == 2
    assert performed["completed_reps"] == 1
    assert performed["work_seconds"] == 40
    assert performed["rest_seconds"] == 20
    assert performed["rest_after_seconds"] == 15
    assert performed["actual_work_seconds"] == 52.5
    assert performed["actual_rest_seconds"] == 20
    assert performed["ended_early"] is True
    assert "weight" in performed


def test_editing_a_comment_does_not_unflag_the_set(client):
    """The feedback edit is the one that must not cost the flag.

    `WorkoutUpdate.is_mobility` defaults to False and every other field on that
    model is a full replace, so a PUT carrying only a comment would clear it -
    and adding feedback to a set after running it is the whole read-back
    channel. The flag would vanish exactly when the loop needs it.
    """
    session_id = write_pending()
    client.post(f"/api/upcoming/session/{session_id}/transfer", json={"date": "2026-08-11"})
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

    assert client.get("/api/mobility/last-session").json() is not None
    still = client.get("/api/workouts/", params={"date": "2026-08-11"}).json()
    assert still[0]["is_mobility"] is True


def test_unflagging_a_set_is_possible_when_actually_asked_for(client):
    session_id = write_pending()
    client.post(f"/api/upcoming/session/{session_id}/transfer", json={"date": "2026-08-11"})
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
    assert client.get("/api/mobility/last-session").json() is None


def test_two_labels_are_two_independent_sessions(client):
    """Rehabbing a low back and a shoulder at once is the whole feature."""
    low = write_pending("QL first", label="Low back")
    shoulder = write_pending("Lock 3 daily", label="Shoulder")
    assert low != shoulder

    queue = client.get("/api/upcoming/").json()
    assert [s["label"] for s in queue] == ["Low back", "Shoulder"]

    # Transferring one leaves the other pending.
    client.post(f"/api/upcoming/session/{low}/transfer", json={"date": "2026-08-11"})
    after = client.get("/api/upcoming/").json()
    assert [s["label"] for s in after] == ["Shoulder"]


def test_discarding_one_session_leaves_the_other(client):
    write_pending("QL first", label="Low back")
    shoulder = write_pending("Lock 3 daily", label="Shoulder")

    assert client.delete(f"/api/upcoming/session/{shoulder}").status_code == 204

    queue = client.get("/api/upcoming/").json()
    assert [s["label"] for s in queue] == ["Low back"]


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
    assert client.get("/api/mobility/last-session").json()["date"] == "2026-08-11"


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
    assert client.get("/api/mobility/last-session").json() is None


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

    response = client.get("/api/mobility/last-session")

    assert response.status_code == 200
    assert response.json()["rationale"] is None


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
            text("SELECT COUNT(*) FROM upcoming_workouts WHERE is_mobility = 1")
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
    queue = client.get("/api/upcoming/").json()
    by_label = {s["label"]: s for s in queue}
    assert [i["exercise"] for i in by_label["Low back"]["items"]] == ["Hip Thrust"]
    assert by_label["Low back"]["rationale"] == "revised"
    # The other label is untouched: same session number, same three rows.
    assert by_label["Shoulder"]["session"] == shoulder
    assert len(by_label["Shoulder"]["items"]) == 3


def test_a_new_session_numbers_above_the_whole_queue(client):
    """One namespace now (9c4e7b21f806): a fresh label takes the global max +
    1, not the next number within mobility, so it can never collide with a
    Liftoscript session for transfer or delete to hit both."""
    client.post(
        "/api/upcoming/",
        json={"session": 7, "exercise": "Bench", "category": "Push"},
    )

    body = client.post("/api/mobility/pending", json=session_body()).json()

    assert body["session"] == 8


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

    (session,) = client.get("/api/upcoming/").json()
    assert [(i["exercise"], i["reps"], i["weight"]) for i in session["items"]] == [
        ("Dead Bug", 20, 25.0),
        ("Dead Bug", 15, 25.0),
        ("Dead Bug", 15, 25.0),
    ]
    assert all(i["comment"] is None for i in session["items"])


def test_an_item_can_be_prescribed_unflagged(client):
    """Every workout has a mobility element — not every set in it is one. A
    session can prescribe lifting sets alongside the mobility work, and the
    flag travels per item."""
    client.post(
        "/api/mobility/pending",
        json=session_body(
            items=[
                {"exercise": "Romanian Deadlift", "reps": 8, "weight_lb": 135,
                 "mobility": False},
                {"exercise": "Pigeon Squat", "reps": 5, "weight_lb": 30},
            ]
        ),
    )

    (session,) = client.get("/api/upcoming/").json()
    assert [(i["exercise"], i["is_mobility"]) for i in session["items"]] == [
        ("Romanian Deadlift", False),
        ("Pigeon Squat", True),
    ]


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
    (session,) = client.get("/api/upcoming/").json()
    # The existing movement, under its own name and its own category.
    assert (session["items"][0]["exercise"], session["items"][0]["category"]) == (
        "Dead Bug",
        "Legs",
    )


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

    (session,) = client.get("/api/upcoming/").json()
    assert [(i["exercise"], i["category"]) for i in session["items"]] == [
        ("Copenhagen Plank", "Core"),
        ("Couch Stretch", "Uncategorized"),
    ]


def test_a_written_session_shows_on_the_queue_and_transfers(client):
    session_id = client.post("/api/mobility/pending", json=session_body()).json()[
        "session"
    ]

    queue = client.get("/api/upcoming/").json()
    assert queue[0]["session"] == session_id
    assert queue[0]["label"] == "Low back"

    response = client.post(
        f"/api/upcoming/session/{session_id}/transfer", json={"date": "2026-09-25"}
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
    last = client.get("/api/mobility/last-session").json()
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


# --- Movement break suggestions (plan 0018) -----------------------------------
#
# The old `POST /movement-break` wrote a *finished* run: one completed row per
# interval. The suggestion replaces it: an ordinary planned tile holding the
# movement's defaults, which the day player performs like anything else.


def _enpool(client, name, category="Legs", **overrides):
    body = {
        "name": name,
        "category": category,
        "movement_break_enabled": True,
        "time_enabled": True,
        "default_work_seconds": 40,
        "default_reps": 2,
        "default_rest_seconds": 20,
    }
    body.update(overrides)
    response = client.post("/api/exercises/", json=body)
    assert response.status_code == 201
    return response.json()


def test_a_suggestion_is_an_incomplete_mobility_tile_holding_the_defaults(client):
    _enpool(
        client,
        "Farmer Carry",
        default_weight_lb=None,
        default_rest_after_seconds=15,
    )
    # Something already on the day, so "appended" is distinguishable from
    # "inserted".
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

    response = client.post("/api/mobility/suggest", json={"date": "2026-11-12"})
    assert response.status_code == 201
    tile = response.json()

    assert tile["exercise"] == "Farmer Carry"
    assert tile["is_mobility"] is True
    # The exercise's defaults, not a finished run: nothing is performed yet.
    assert tile["reps"] == 2
    assert tile["weight"] is None  # filled in on the day, not defaulted
    assert tile["work_seconds"] == 40
    assert tile["rest_seconds"] == 20
    assert tile["rest_after_seconds"] == 15
    assert tile["completed_at"] is None
    assert tile["completed_reps"] is None

    day = client.get("/api/workouts/?date=2026-11-12").json()
    squat = next(w for w in day if w["exercise"] == "Barbell Squat")
    assert tile["order"] > squat["order"]


def test_a_suggestion_is_not_work_until_performed(client):
    """An unused suggestion must not affect the shuffle's `last_used`, the
    use count, or the calendar (plan 0018)."""
    _enpool(client, "Deep Squat Hold")

    client.post("/api/mobility/suggest", json={"date": "2026-11-12"})

    movement = client.get("/api/exercises/Deep Squat Hold").json()
    assert movement["last_used"] is None
    assert movement["use_count"] == 0
    calendar = client.get("/api/workouts/calendar?year=2026&month=11").json()
    assert calendar["counts"] == {}


def test_the_shuffle_prefers_the_least_recently_used(client):
    """Three candidates and the least recently used of them; with three in the
    pool the draw always sees all three, so the pick is deterministic."""
    _enpool(client, "Deep Squat Hold")
    _enpool(client, "Wall Angel", category="Shoulders")
    _enpool(client, "Chin Tuck", category="Back")
    # Wall Angel was performed most recently; Deep Squat Hold before it. Chin
    # Tuck has never been done, which outranks both.
    for name, date in (("Wall Angel", "2026-11-12"), ("Deep Squat Hold", "2026-11-01")):
        created = client.post(
            "/api/workouts/",
            json={"date": date, "exercise": name, "category": "Legs",
                  "completed_at": "2026-11-12T12:00:00"},
        ).json()
        assert created["completed_at"] is not None

    for _ in range(5):
        response = client.post("/api/mobility/suggest", json={"date": "2026-11-13"})
        assert response.json()["exercise"] == "Chin Tuck"


def test_an_empty_pool_is_a_404_and_writes_nothing(client):
    response = client.post("/api/mobility/suggest", json={"date": "2026-11-12"})
    assert response.status_code == 404
    assert client.get("/api/workouts/?date=2026-11-12").json() == []


def test_a_suggestion_defaults_to_today(client):
    _enpool(client, "Plank", category="Core")

    response = client.post("/api/mobility/suggest", json={})
    assert response.status_code == 201
    # The app's timezone, never the client's guess at a date.
    assert response.json()["date"] == get_current_date()
