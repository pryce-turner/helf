import pytest

from app import database
from app.db.models import Workout
from app.models.workout import WorkoutCreate, WorkoutUpdate
from app.repositories.workout_repo import WorkoutRepository

pytestmark = pytest.mark.usefixtures("db_engine")


def _create_workout(repo, date, exercise, category, reps=5, order=None, weight=100):
    return repo.create(
        WorkoutCreate(
            date=date,
            exercise=exercise,
            category=category,
            reps=reps,
            weight=weight,
            order=order,
        )
    )


def test_workout_create_defaults_order(db_session):
    repo = WorkoutRepository()
    first = _create_workout(repo, "2024-01-01", "Bench", "Push")
    second = _create_workout(repo, "2024-01-01", "Bench", "Push")

    assert first["order"] == 1
    assert second["order"] == 2

    stored = db_session.query(Workout).filter(Workout.id == first["doc_id"]).one()
    assert stored.reps == 5


def test_workout_update_preserves_order_when_missing():
    repo = WorkoutRepository()
    created = _create_workout(repo, "2024-01-02", "Squat", "Legs", order=3)

    updated = repo.update(
        created["doc_id"],
        WorkoutUpdate(
            date="2024-01-02",
            exercise="Front Squat",
            category="Legs",
            reps=5,
            weight=120,
        ),
    )

    assert updated["order"] == 3
    assert updated["exercise"] == "Front Squat"
    assert updated["reps"] == 5


def test_workout_toggle_complete_updates_timestamp():
    repo = WorkoutRepository()
    created = _create_workout(repo, "2024-01-03", "Deadlift", "Pull")

    completed = repo.toggle_complete(created["doc_id"], True)
    assert completed["completed_at"] is not None

    cleared = repo.toggle_complete(created["doc_id"], False)
    assert cleared["completed_at"] is None


def test_workout_reorder_swaps_positions():
    repo = WorkoutRepository()
    first = _create_workout(repo, "2024-01-04", "Row", "Pull")
    second = _create_workout(repo, "2024-01-04", "Curl", "Pull")

    assert repo.reorder(second["doc_id"], "2024-01-04", "up") is True
    reordered = repo.get_by_date("2024-01-04")
    assert [w["doc_id"] for w in reordered] == [second["doc_id"], first["doc_id"]]


def test_workout_reorder_blocks_out_of_range():
    repo = WorkoutRepository()
    first = _create_workout(repo, "2024-01-05", "Row", "Pull")
    assert repo.reorder(first["doc_id"], "2024-01-05", "up") is False


def test_workout_bulk_reorder_updates_order():
    repo = WorkoutRepository()
    first = _create_workout(repo, "2024-01-06", "Row", "Pull")
    second = _create_workout(repo, "2024-01-06", "Curl", "Pull")

    assert repo.bulk_reorder([]) is False
    assert repo.bulk_reorder([second["doc_id"], first["doc_id"]]) is True

    reordered = repo.get_by_date("2024-01-06")
    assert [w["doc_id"] for w in reordered] == [second["doc_id"], first["doc_id"]]


def test_workout_move_to_date_appends_orders():
    repo = WorkoutRepository()
    _create_workout(repo, "2024-01-07", "Row", "Pull")
    _create_workout(repo, "2024-01-07", "Curl", "Pull")
    _create_workout(repo, "2024-01-08", "Press", "Push")

    moved = repo.move_to_date("2024-01-07", "2024-01-08")
    assert moved == 2

    target = repo.get_by_date("2024-01-08")
    assert [w["order"] for w in target] == [1, 2, 3]


def test_workout_counts_by_date_groups_correctly():
    repo = WorkoutRepository()
    _create_workout(repo, "2024-02-01", "Row", "Pull")
    _create_workout(repo, "2024-02-01", "Curl", "Pull")
    _create_workout(repo, "2024-02-02", "Press", "Push")

    counts = repo.get_workout_counts_by_date(2024, 2)
    assert counts == {"2024-02-01": 2, "2024-02-02": 1}


def test_workout_get_by_exercise_orders_by_date():
    repo = WorkoutRepository()
    _create_workout(repo, "2024-02-03", "Bench", "Push")
    _create_workout(repo, "2024-02-01", "Bench", "Push")

    results = repo.get_by_exercise("Bench")
    assert [w["date"] for w in results] == ["2024-02-01", "2024-02-03"]


def _day_orders(repo, date):
    return [(w["weight"], w["order"]) for w in repo.get_by_date(date)]


def _create_after_completed(repo, date, weight):
    return _create_workout(repo, date, "Bench", "Push", weight=weight)


def test_create_after_last_completed_inserts_below_bottom_completed_set():
    repo = WorkoutRepository()
    date = "2024-02-01"
    sets = [_create_workout(repo, date, "Bench", "Push", weight=w) for w in (1, 2, 3, 4)]
    # Completed out of position order: the anchor is the lowest ticked set by
    # position (3), not the one ticked most recently (1).
    repo.toggle_complete(sets[2]["doc_id"], True)
    repo.toggle_complete(sets[0]["doc_id"], True)

    created = _create_after_completed(repo, date, 99)

    assert created["order"] == 4
    assert _day_orders(repo, date) == [(1, 1), (2, 2), (3, 3), (99, 4), (4, 5)]


def test_create_after_last_completed_appends_when_nothing_completed():
    repo = WorkoutRepository()
    date = "2024-02-02"
    for w in (1, 2):
        _create_workout(repo, date, "Bench", "Push", weight=w)

    _create_after_completed(repo, date, 99)

    assert _day_orders(repo, date) == [(1, 1), (2, 2), (99, 3)]


def test_create_after_last_completed_moves_only_colliding_sets():
    """A gap below the slot absorbs the shift, so nothing past it is rewritten."""
    repo = WorkoutRepository()
    date = "2024-02-03"
    done = _create_workout(repo, date, "Bench", "Push", weight=1, order=1)
    _create_workout(repo, date, "Bench", "Push", weight=2, order=2)
    _create_workout(repo, date, "Bench", "Push", weight=3, order=10)
    repo.toggle_complete(done["doc_id"], True)

    _create_after_completed(repo, date, 99)

    assert _day_orders(repo, date) == [(1, 1), (99, 2), (2, 3), (3, 10)]


def test_explicit_order_is_not_repositioned():
    repo = WorkoutRepository()
    date = "2024-02-04"
    first = _create_workout(repo, date, "Bench", "Push", weight=1)
    repo.toggle_complete(first["doc_id"], True)

    created = repo.create(
        WorkoutCreate(
            date=date, exercise="Bench", category="Push", weight=99, order=7,
        )
    )

    assert created["order"] == 7


def test_creating_a_set_maintains_the_movement_usage():
    """`update_usage` had no caller, so `exercises.last_used` was a year stale
    — max 2025-12-21 against sets logged through today — which made
    `GET /exercises/recent` answer from December and put the wrong movements
    first in the day view's add form. It is maintained where the set is
    written, because that is the only place it can be."""
    from app.db.models import Exercise

    repo = WorkoutRepository()
    _create_workout(repo, "2026-11-12", "Cossack Squat", "Legs")
    _create_workout(repo, "2026-11-12", "Cossack Squat", "Legs")

    with database.SessionLocal() as session:
        exercise = session.query(Exercise).filter(
            Exercise.name == "Cossack Squat"
        ).one()
        assert exercise.last_used == "2026-11-12"
        assert exercise.use_count == 2
