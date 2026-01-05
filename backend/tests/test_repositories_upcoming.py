import pytest

from app.db.models import UpcomingWorkout
from app.models.upcoming import UpcomingWorkoutCreate
from app.repositories.upcoming_repo import UpcomingWorkoutRepository

pytestmark = pytest.mark.usefixtures("db_engine")


def test_upcoming_create_converts_reps(db_session):
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
    assert stored.reps == "5"
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
