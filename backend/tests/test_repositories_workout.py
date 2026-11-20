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
    first = _create_workout(repo, "2024-02-01", "Row", "Pull")
    second = _create_workout(repo, "2024-02-01", "Curl", "Pull")
    third = _create_workout(repo, "2024-02-02", "Press", "Push")
    # The calendar reports performed work, not planned tiles (plan 0018).
    for created in (first, second, third):
        repo.toggle_complete(created["doc_id"], True)

    counts = repo.get_workout_counts_by_date(2024, 2)
    assert counts == {"2024-02-01": 2, "2024-02-02": 1}


def test_workout_get_by_exercise_orders_by_date():
    repo = WorkoutRepository()
    second = _create_workout(repo, "2024-02-03", "Bench", "Push")
    first = _create_workout(repo, "2024-02-01", "Bench", "Push")
    # History is performed work (plan 0018), so both are completed here.
    repo.toggle_complete(second["doc_id"], True)
    repo.toggle_complete(first["doc_id"], True)

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
    """Usage moves at performance time, not suggestion time (plan 0018): an
    unplayed tile must not affect the next shuffle or the recent list, so the
    write happens where the set is *performed*, not where it is planned."""
    from app.db.models import Exercise

    repo = WorkoutRepository()
    _create_workout(repo, "2026-11-12", "Cossack Squat", "Legs")
    second = _create_workout(repo, "2026-11-12", "Cossack Squat", "Legs")

    with database.SessionLocal() as session:
        exercise = session.query(Exercise).filter(
            Exercise.name == "Cossack Squat"
        ).one()
        assert exercise.last_used is None
        assert exercise.use_count == 0

    repo.toggle_complete(second["doc_id"], True)

    with database.SessionLocal() as session:
        exercise = session.query(Exercise).filter(
            Exercise.name == "Cossack Squat"
        ).one()
        assert exercise.last_used == "2026-11-12"
        assert exercise.use_count == 1


# --- Target vs actual (plan 0018) -------------------------------------------

from app.utils.date_helpers import get_current_date


def _create_timed(repo, date, exercise="Farmer Carry", category="Legs", **kwargs):
    # The tile can only carry what the exercise offers (plan 0018): Time is
    # enabled on it here, or create would null the timing fields.
    from app.models.exercise import ExerciseUpdate
    from app.repositories.exercise_repo import ExerciseRepository

    exercise_repo = ExerciseRepository()
    existing = exercise_repo.get_by_name(exercise)
    if existing is None:
        from app.models.exercise import ExerciseCreate

        exercise_repo.create(
            ExerciseCreate(name=exercise, category=category, time_enabled=True)
        )
    elif not existing["time_enabled"]:
        exercise_repo.update(existing["doc_id"], ExerciseUpdate(time_enabled=True))

    defaults = dict(
        reps=2,
        weight=None,
        work_seconds=40,
        rest_seconds=20,
        rest_after_seconds=15,
    )
    defaults.update(kwargs)
    return repo.create(
        WorkoutCreate(date=date, exercise=exercise, category=category, **defaults)
    )


def test_targets_round_trip_on_create_and_read_back():
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-01")

    assert created["work_seconds"] == 40
    assert created["rest_seconds"] == 20
    assert created["rest_after_seconds"] == 15
    # Nothing performed yet: every actual is empty and the tile is planned.
    assert created["completed_reps"] is None
    assert created["actual_work_seconds"] is None
    assert created["ended_early"] is False

    fetched = repo.get_by_id(created["doc_id"])
    assert fetched["rest_after_seconds"] == 15


def test_a_disabled_group_cannot_be_filled_on_create():
    """Ordinary manual creation can fill only enabled fields (plan 0018). The
    UI does not offer them, and the server is the second line — a caller with
    a stale configuration loses the value rather than writing a tile the
    movement says it does not take."""
    repo = WorkoutRepository()
    # A fresh exercise is Reps/Weight enabled and Time/Distance disabled.
    created = repo.create(
        WorkoutCreate(
            date="2024-03-02",
            exercise="Bench",
            category="Push",
            reps=5,
            weight=100,
            work_seconds=40,
            distance=100.0,
        )
    )

    assert created["reps"] == 5
    assert created["weight"] == 100
    assert created["work_seconds"] is None
    assert created["distance"] is None


def test_manual_completion_derives_actuals_from_targets():
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-03")

    done = repo.toggle_complete(created["doc_id"], True)
    assert done["completed_at"] is not None
    assert done["completed_reps"] == 2
    # Totals, not per-rep targets: two 40s reps is 80s of work, and the rest
    # runs only between them, so once.
    assert done["actual_work_seconds"] == 80
    assert done["actual_rest_seconds"] == 20
    # The rest-after is the divider's own performance, recorded separately.
    assert done["actual_rest_after_seconds"] is None
    assert done["ended_early"] is False
    # A manual tick does not move the tile's date — that rule is the player's.
    assert done["date"] == "2024-03-03"


def test_uncompleting_a_tile_clears_its_performance():
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-04")
    repo.toggle_complete(created["doc_id"], True)

    planned = repo.toggle_complete(created["doc_id"], False)
    assert planned["completed_at"] is None
    assert planned["completed_reps"] is None
    assert planned["actual_work_seconds"] is None
    assert planned["actual_rest_seconds"] is None
    assert planned["ended_early"] is False
    # The targets survive — it is a planned tile again, not a blank one.
    assert planned["work_seconds"] == 40


def test_perform_natural_completion_derives_and_moves_to_today():
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-05")

    performed = repo.perform(created["doc_id"], ended_early=False)
    today = get_current_date()
    assert performed["date"] == today
    assert performed["completed_at"] is not None
    assert performed["completed_reps"] == 2
    assert performed["actual_work_seconds"] == 80
    assert performed["actual_rest_seconds"] == 20
    assert performed["ended_early"] is False
    # The targets survive playback: what was planned and what was done stay
    # distinguishable.
    assert performed["reps"] == 2
    assert performed["work_seconds"] == 40


def test_perform_stopped_keeps_the_measured_actuals():
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-06")

    performed = repo.perform(
        created["doc_id"],
        ended_early=True,
        completed_reps=1,
        actual_work_seconds=52.4,
        actual_rest_seconds=20,
    )
    assert performed["ended_early"] is True
    assert performed["completed_reps"] == 1
    assert performed["actual_work_seconds"] == 52.4
    assert performed["actual_rest_seconds"] == 20
    # Target untouched: the shortfall is target minus actual, not a rewrite.
    assert performed["reps"] == 2


def test_perform_bumps_usage_once_at_performance():
    from app.db.models import Exercise

    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-07")
    repo.perform(created["doc_id"], ended_early=False)

    with database.SessionLocal() as session:
        exercise = session.query(Exercise).filter(
            Exercise.name == "Farmer Carry"
        ).one()
        assert exercise.use_count == 1
        assert exercise.last_used == get_current_date()


def test_rest_after_records_on_the_performed_tile():
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-08")
    repo.perform(created["doc_id"], ended_early=False)

    updated = repo.record_rest_after(created["doc_id"], 7.5)
    assert updated["actual_rest_after_seconds"] == 7.5
    # A full rest-after run records the whole thing.
    updated = repo.record_rest_after(created["doc_id"], 15)
    assert updated["actual_rest_after_seconds"] == 15


def test_rest_after_refuses_a_tile_that_has_not_run():
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-09")

    with pytest.raises(ValueError, match="not performed"):
        repo.record_rest_after(created["doc_id"], 7.5)


def test_copy_to_date_resets_performance_but_keeps_targets():
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-10")
    # The manual tick, not `perform`: the player moves the tile to today,
    # which is not what a copy-from-a-named-date test can use.
    repo.toggle_complete(created["doc_id"], True)

    assert repo.copy_to_date("2024-03-10", "2024-03-11") == 1
    (copied,) = repo.get_by_date("2024-03-11")
    assert copied["work_seconds"] == 40
    assert copied["rest_seconds"] == 20
    assert copied["rest_after_seconds"] == 15
    assert copied["reps"] == 2
    # A copy is a planned tile: no completion, no actuals, no early flag.
    assert copied["completed_at"] is None
    assert copied["completed_reps"] is None
    assert copied["actual_work_seconds"] is None
    assert copied["ended_early"] is False


def test_update_preserves_performance_and_replaces_targets():
    """Editing a performed tile's targets or comment is not a performance
    write — actuals are the player's and the tick's, not the edit form's."""
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-12")
    repo.perform(created["doc_id"], ended_early=True, completed_reps=1)

    updated = repo.update(
        created["doc_id"],
        WorkoutUpdate(
            date="2024-03-12",
            exercise="Farmer Carry",
            category="Legs",
            reps=3,
            work_seconds=45,
            comment="cut at 1, shoulder",
        ),
    )
    assert updated["reps"] == 3
    assert updated["work_seconds"] == 45
    assert updated["comment"] == "cut at 1, shoulder"
    assert updated["completed_reps"] == 1
    assert updated["ended_early"] is True


def test_counts_and_history_report_performed_work_only():
    repo = WorkoutRepository()
    planned = _create_workout(repo, "2024-03-13", "Bench", "Push")
    done = _create_workout(repo, "2024-03-13", "Bench", "Push")
    repo.toggle_complete(done["doc_id"], True)

    assert repo.get_workout_counts_by_date(2024, 3) == {"2024-03-13": 1}
    history = repo.get_by_exercise("Bench")
    assert [w["doc_id"] for w in history] == [done["doc_id"]]
    assert planned["doc_id"] not in [w["doc_id"] for w in history]


# --- Idempotency and legacy-field discipline ---------------------------------


def test_perform_is_idempotent_on_an_already_performed_tile():
    """A lost response makes the client's Retry repeat the write; the second
    one must come back as the first did — same completion, same date, same
    order — not as a fresh performance that double-counts the movement."""
    from app.db.models import Exercise

    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-14")
    first = repo.perform(created["doc_id"], ended_early=False)

    second = repo.perform(created["doc_id"], ended_early=False)
    assert second["doc_id"] == first["doc_id"]
    assert second["completed_at"] == first["completed_at"]
    assert second["date"] == first["date"]
    assert second["order"] == first["order"]

    with database.SessionLocal() as session:
        exercise = session.query(Exercise).filter(
            Exercise.name == "Farmer Carry"
        ).one()
        assert exercise.use_count == 1


def test_toggle_complete_on_a_completed_tile_preserves_measured_actuals():
    """Ticking an already-ticked tile must not overwrite the player's measured
    actuals with derived ones, and must not count the movement a second time."""
    from app.db.models import Exercise

    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-15")
    repo.perform(
        created["doc_id"],
        ended_early=True,
        completed_reps=1,
        actual_work_seconds=52.5,
        actual_rest_seconds=20,
    )

    again = repo.toggle_complete(created["doc_id"], True)
    assert again["completed_reps"] == 1
    assert again["actual_work_seconds"] == 52.5
    assert again["ended_early"] is True

    with database.SessionLocal() as session:
        exercise = session.query(Exercise).filter(
            Exercise.name == "Farmer Carry"
        ).one()
        assert exercise.use_count == 1


def test_uncompleting_clears_every_actual_including_the_divider():
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-16")
    repo.perform(created["doc_id"], ended_early=False)
    repo.record_rest_after(created["doc_id"], 7.5)

    planned = repo.toggle_complete(created["doc_id"], False)
    assert planned["completed_at"] is None
    assert planned["completed_reps"] is None
    assert planned["actual_work_seconds"] is None
    assert planned["actual_rest_seconds"] is None
    assert planned["actual_rest_after_seconds"] is None
    assert planned["ended_early"] is False


def test_time_is_legacy_read_only_on_create_and_update():
    """`time` stays in responses for old rows but is never written any more
    (plan 0018): null accepted for compatibility, a value ignored."""
    repo = WorkoutRepository()
    created = repo.create(
        WorkoutCreate(
            date="2024-03-17", exercise="Plank", category="Core", time="0:30"
        )
    )
    assert created["time"] is None

    # A row that genuinely has a legacy value keeps it through edits.
    with database.SessionLocal() as session:
        row = session.get(Workout, created["doc_id"])
        row.time = "0:30"
        session.commit()

    updated = repo.update(
        created["doc_id"],
        WorkoutUpdate(
            date="2024-03-17",
            exercise="Plank",
            category="Core",
            comment="held steady",
        ),
    )
    assert updated["time"] == "0:30"
    assert updated["comment"] == "held steady"


def test_timing_targets_are_sticky_when_omitted_from_an_update():
    """An older client that does not know the new fields must not wipe them by
    omitting them; sending an explicit null is how one clears."""
    repo = WorkoutRepository()
    created = _create_timed(repo, "2024-03-18")

    updated = repo.update(
        created["doc_id"],
        WorkoutUpdate(
            date="2024-03-18",
            exercise="Farmer Carry",
            category="Legs",
            comment="comment only",
        ),
    )
    assert updated["work_seconds"] == 40
    assert updated["rest_seconds"] == 20
    assert updated["rest_after_seconds"] == 15

    cleared = repo.update(
        created["doc_id"],
        WorkoutUpdate(
            date="2024-03-18",
            exercise="Farmer Carry",
            category="Legs",
            work_seconds=None,
            rest_after_seconds=None,
        ),
    )
    assert cleared["work_seconds"] is None
    assert cleared["rest_after_seconds"] is None
    # Omitted again here: untouched by the second write as well.
    assert cleared["rest_seconds"] == 20
