import pytest

from app.db.models import UpcomingWorkout
from app.models.upcoming import UpcomingWorkoutCreate
from app.repositories.upcoming_repo import UpcomingWorkoutRepository

pytestmark = pytest.mark.usefixtures("db_engine")


def test_upcoming_create_stores_reps_as_integer(db_session):
    """reps is an integer end to end - no string round-trip (ADR-0005)."""
    repo = UpcomingWorkoutRepository()
    created = repo.create(
        UpcomingWorkoutCreate(
            session=1,
            exercise="Bench",
            category="Push",
            reps=5,
            weight=100,
        )
    )

    stored = db_session.query(UpcomingWorkout).filter(UpcomingWorkout.id == created["doc_id"]).one()
    assert stored.reps == 5
    assert isinstance(stored.reps, int)
    assert created["reps"] == 5


def test_upcoming_create_bulk_and_get_lowest_session():
    repo = UpcomingWorkoutRepository()
    workouts = repo.create_bulk(
        [
            UpcomingWorkoutCreate(session=3, exercise="Bench", category="Push"),
            UpcomingWorkoutCreate(session=2, exercise="Squat", category="Legs"),
        ]
    )
    assert len(workouts) == 2
    assert repo.get_lowest_session() == 2


def test_upcoming_delete_session_removes_all():
    repo = UpcomingWorkoutRepository()
    repo.create(UpcomingWorkoutCreate(session=1, exercise="Row", category="Pull"))
    repo.create(UpcomingWorkoutCreate(session=1, exercise="Curl", category="Pull"))

    deleted = repo.delete_session(1)
    assert deleted == 2
    assert repo.get_all() == []


def test_upcoming_get_by_exercise_orders_by_session():
    repo = UpcomingWorkoutRepository()
    repo.create(UpcomingWorkoutCreate(session=2, exercise="Bench", category="Push"))
    repo.create(UpcomingWorkoutCreate(session=1, exercise="Bench", category="Push"))

    results = repo.get_by_exercise("Bench")
    assert [r["session"] for r in results] == [1, 2]


# --------------------------------------------------------------------------
# `kind` scoping
#
# Lifting and mobility share this table (Plan 0012 §2), so every method is
# scoped and the default is 'lifting'. These are the tests that fail if a
# `.where(kind == ...)` is dropped — otherwise the two programs silently mix
# and the symptom appears somewhere else entirely.
# --------------------------------------------------------------------------
def _one_of_each(repo: UpcomingWorkoutRepository) -> None:
    repo.create(UpcomingWorkoutCreate(session=1, exercise="Bench", category="Push"))
    repo.create(
        UpcomingWorkoutCreate(
            session=1, kind="mobility", exercise="QL Raise", category="Core"
        )
    )


def test_kind_defaults_to_lifting():
    repo = UpcomingWorkoutRepository()
    created = repo.create(UpcomingWorkoutCreate(session=1, exercise="Bench", category="Push"))

    assert created["kind"] == "lifting"


def test_get_all_returns_one_kind_at_a_time():
    repo = UpcomingWorkoutRepository()
    _one_of_each(repo)

    assert [w["exercise"] for w in repo.get_all()] == ["Bench"]
    assert [w["exercise"] for w in repo.get_all(kind="mobility")] == ["QL Raise"]


def test_delete_all_does_not_cross_kinds():
    """The Liftoscript generator's clear-the-board step. Unscoped, generating a
    lifting program would destroy the pending mobility session."""
    repo = UpcomingWorkoutRepository()
    _one_of_each(repo)

    assert repo.delete_all() == 1
    assert [w["exercise"] for w in repo.get_all(kind="mobility")] == ["QL Raise"]


def test_delete_session_does_not_cross_kinds():
    """Both programs happen to use session 1, so this one is easy to get wrong."""
    repo = UpcomingWorkoutRepository()
    _one_of_each(repo)

    assert repo.delete_session(1) == 1
    assert len(repo.get_by_session(1, kind="mobility")) == 1


def test_get_by_exercise_excludes_mobility_by_default():
    """Its caller projects a 1RM curve forward. A prescribed stretch at
    bodyweight is not a point on that curve."""
    repo = UpcomingWorkoutRepository()
    repo.create(
        UpcomingWorkoutCreate(
            session=1, kind="mobility", exercise="Good Morning", category="Back"
        )
    )

    assert repo.get_by_exercise("Good Morning") == []


def test_creating_a_mobility_row_flags_a_new_exercise(db_session):
    from app.db.models import Exercise

    UpcomingWorkoutRepository().create(
        UpcomingWorkoutCreate(
            session=1, kind="mobility", exercise="Copenhagen Raise", category="Core"
        )
    )

    exercise = (
        db_session.query(Exercise).filter(Exercise.name == "Copenhagen Raise").one()
    )
    assert exercise.is_mobility is True


def test_creating_a_mobility_row_leaves_an_existing_flag_alone(db_session):
    from app.db.models import Exercise

    repo = UpcomingWorkoutRepository()
    repo.create(UpcomingWorkoutCreate(session=1, exercise="Good Morning", category="Back"))
    repo.create(
        UpcomingWorkoutCreate(
            session=1, kind="mobility", exercise="Good Morning", category="Back"
        )
    )

    exercise = db_session.query(Exercise).filter(Exercise.name == "Good Morning").one()
    assert exercise.is_mobility is False
