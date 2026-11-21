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
# One queue (9c4e7b21f806)
#
# The `kind` split is gone: lifting and mobility rows list together, and
# whether a planned set is mobility work is a flag on the row, not a program
# it belongs to. These pin the unified behaviour — reads return everything,
# `delete_all` really clears the board, and the progression read still
# excludes mobility sets.
# --------------------------------------------------------------------------
def _one_of_each(repo: UpcomingWorkoutRepository) -> None:
    repo.create(UpcomingWorkoutCreate(session=1, exercise="Bench", category="Push"))
    repo.create(
        UpcomingWorkoutCreate(
            session=2, is_mobility=True, exercise="QL Raise", category="Core"
        )
    )


def test_is_mobility_defaults_to_false():
    repo = UpcomingWorkoutRepository()
    created = repo.create(UpcomingWorkoutCreate(session=1, exercise="Bench", category="Push"))

    assert created["is_mobility"] is False


def test_get_all_returns_the_whole_queue():
    repo = UpcomingWorkoutRepository()
    _one_of_each(repo)

    assert [w["exercise"] for w in repo.get_all()] == ["Bench", "QL Raise"]


def test_delete_all_clears_the_whole_queue():
    """The Liftoscript generator's clear-the-board step really clears it now —
    the route deletes the plans alongside, and the page warns before
    confirming (9c4e7b21f806)."""
    repo = UpcomingWorkoutRepository()
    _one_of_each(repo)

    assert repo.delete_all() == 2
    assert repo.get_all() == []


def test_delete_session_takes_that_session_whatever_its_flag():
    """A session is one number in one namespace; deleting it cannot leave a
    mobility row behind because of a flag the method did not check."""
    repo = UpcomingWorkoutRepository()
    repo.create(UpcomingWorkoutCreate(session=1, exercise="Bench", category="Push"))
    repo.create(
        UpcomingWorkoutCreate(
            session=1, is_mobility=True, exercise="QL Raise", category="Core"
        )
    )

    assert repo.delete_session(1) == 2
    assert repo.get_by_session(1) == []


def test_get_by_exercise_excludes_mobility_sets():
    """Its caller projects a 1RM curve forward. A prescribed stretch at
    bodyweight is not a point on that curve."""
    repo = UpcomingWorkoutRepository()
    repo.create(
        UpcomingWorkoutCreate(
            session=1, is_mobility=True, exercise="Good Morning", category="Back"
        )
    )
    repo.create(
        UpcomingWorkoutCreate(session=2, exercise="Good Morning", category="Back")
    )

    assert [w["session"] for w in repo.get_by_exercise("Good Morning")] == [2]


def test_a_mobility_row_records_nothing_on_the_exercise(db_session):
    """Planning a movement as mobility work says nothing about the movement.

    The flag lives on the planned row and becomes `workouts.is_mobility` at
    transfer. The same good morning can be prescribed as a loaded stretch this
    week and pulled heavy the next, and one exercise row serves both.
    """
    from app.db.models import Exercise

    UpcomingWorkoutRepository().create(
        UpcomingWorkoutCreate(
            session=1, is_mobility=True, exercise="Copenhagen Raise", category="Core"
        )
    )

    exercise = (
        db_session.query(Exercise).filter(Exercise.name == "Copenhagen Raise").one()
    )
    assert not hasattr(exercise, "is_mobility")
