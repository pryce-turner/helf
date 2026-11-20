"""`v_daily_summary` - the object the design doc calls the single most useful
thing to hand the LLM. Its whole job is to join domains that are stored apart,
so the tests are about the joins, not the arithmetic."""

import pytest
from sqlalchemy import text

from app import database
from app.db.models import Metric, Observation
from app.models.food import FoodCreate, FoodLogCreate
from app.models.note import NoteCreate
from app.repositories.food_repo import FoodLogRepository, FoodRepository
from app.repositories.note_repo import NoteRepository
from app.utils.date_helpers import get_current_datetime

pytestmark = pytest.mark.usefixtures("db_engine")


def _row(date: str):
    with database.SessionLocal() as session:
        return session.execute(
            text("SELECT * FROM v_daily_summary WHERE date = :d"), {"d": date}
        ).one_or_none()


def _observe(observed_at: str, source: str, **metrics) -> None:
    with database.SessionLocal() as session:
        observation = Observation(
            observed_at=observed_at, source=source, created_at=get_current_datetime()
        )
        for name, value in metrics.items():
            observation.metrics.append(Metric(name=name, value=value))
        session.add(observation)
        session.commit()


def _log_egg(consumed_at: str, servings: float = 2) -> None:
    food = FoodRepository().create(
        FoodCreate(name="Egg", kcal_per_serving=78, protein_g=6.3)
    )
    FoodLogRepository().create(
        FoodLogCreate(food_id=food["doc_id"], servings=servings, consumed_at=consumed_at)
    )


def test_a_day_appears_because_food_was_logged():
    """The spine is a UNION of dates from every domain, so a day that exists
    only in `food_log` still gets a row."""
    _log_egg("2026-08-07T08:00:00")
    row = _row("2026-08-07")
    assert row is not None
    assert row.kcal == 156


def test_a_day_appears_because_a_note_was_written():
    NoteRepository().create(NoteCreate(body="rest day", noted_at="2026-08-07T20:00:00"))
    assert _row("2026-08-07") is not None


def test_body_weight_comes_from_the_last_reading_of_the_day():
    _observe("2026-08-07 07:00:00", "openscale", body_weight_lb=193.0)
    _observe("2026-08-07 12:00:00", "bodyspec", body_weight_lb=191.0)

    row = _row("2026-08-07")
    # One row picked, never an average across instruments - a scale and a DEXA
    # disagree by design and the mean of the two is a number nothing measured.
    assert row.body_weight_lb == 191.0
    assert row.body_weight_source == "bodyspec"


def test_kcal_target_carries_forward_from_the_last_scan_not_the_newest():
    """A target for a day in January must not be computed from a body
    composition measured in March."""
    _observe("2026-01-10 09:00:00", "bodyspec", rmr_kcal_per_day=1900.0)
    _observe("2026-03-10 09:00:00", "bodyspec", rmr_kcal_per_day=1950.0)
    NoteRepository().create(NoteCreate(body="x", noted_at="2026-02-01T08:00:00"))

    assert _row("2026-02-01").kcal_target == 2660.0   # 1900 x 1.4
    assert _row("2026-03-10").kcal_target == 2730.0   # 1950 x 1.4


def test_kcal_target_is_null_before_the_first_scan():
    NoteRepository().create(NoteCreate(body="x", noted_at="2026-01-01T08:00:00"))
    _observe("2026-03-10 09:00:00", "bodyspec", rmr_kcal_per_day=1950.0)

    assert _row("2026-01-01").kcal_target is None


def test_a_day_with_no_food_reports_null_kcal_not_zero():
    """An unlogged day and a fasted day are different facts."""
    _observe("2026-08-07 07:00:00", "openscale", body_weight_lb=193.0)
    row = _row("2026-08-07")
    assert row.kcal is None
    assert row.foods_missing_macros == 0


def test_the_day_endpoint_still_has_a_target_before_anything_is_logged():
    """The view's spine only carries days something happened on, and "today,
    so far" is routinely not one of them - which is exactly when the target is
    worth reading."""
    from app.repositories.food_repo import FoodLogRepository

    _observe("2026-03-10 09:00:00", "bodyspec", rmr_kcal_per_day=1950.0)

    day = FoodLogRepository().day("2026-08-09")
    assert _row("2026-08-09") is None      # not in the view at all
    assert day["totals"]["kcal"] is None
    assert day["totals"]["kcal_target"] == 2730.0


def _log_set(date: str, *, completed: bool, reps: int = 5, weight: float = 100.0) -> None:
    from app.models.workout import WorkoutCreate
    from app.repositories.workout_repo import WorkoutRepository

    repo = WorkoutRepository()
    created = repo.create(
        WorkoutCreate(
            date=date,
            exercise="Bench",
            category="Push",
            reps=reps,
            weight=weight,
        )
    )
    if completed:
        repo.toggle_complete(created["doc_id"], True)


def test_sets_logged_counts_performed_tiles_not_suggestions():
    """A planned tile is not training yet (plan 0018)."""
    _log_set("2026-08-07", completed=True)
    _log_set("2026-08-07", completed=False)

    row = _row("2026-08-07")
    # The day is on the spine — the planned tile exists — but it does not
    # report as work.
    assert row.sets_logged == 1


def test_volume_uses_completed_reps_and_performed_tiles_only():
    _log_set("2026-08-08", completed=False, reps=5, weight=100.0)
    row = _row("2026-08-08")
    assert row.training_volume_lb is None

    # A stopped tile counts what was actually done: 2 of 5 planned reps.
    # `perform` logs work on the day it happens, so the tile moves to today.
    from app.models.workout import WorkoutCreate
    from app.repositories.workout_repo import WorkoutRepository
    from app.utils.date_helpers import get_current_date

    repo = WorkoutRepository()
    tile = repo.create(
        WorkoutCreate(date="2026-08-09", exercise="Bench", category="Push",
                      reps=5, weight=100.0)
    )
    repo.perform(tile["doc_id"], ended_early=True, completed_reps=2)

    assert _row(get_current_date()).training_volume_lb == 200.0
