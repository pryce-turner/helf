import pytest

from app.models.upcoming import UpcomingWorkoutCreate
from app.models.workout import WorkoutCreate
from app.repositories.upcoming_repo import UpcomingWorkoutRepository
from app.repositories.workout_repo import WorkoutRepository
from app.services.progression_service import ProgressionService

pytestmark = pytest.mark.usefixtures("db_engine")


def test_progression_data_selects_best_set_per_date():
    workout_repo = WorkoutRepository()
    workout_repo.create(
        WorkoutCreate(
            date="2024-01-01",
            exercise="Bench",
            category="Push",
            weight=100,
            reps=5,
        )
    )
    workout_repo.create(
        WorkoutCreate(
            date="2024-01-01",
            exercise="Bench",
            category="Push",
            weight=110,
            reps=3,
        )
    )
    workout_repo.create(
        WorkoutCreate(
            date="2024-01-03",
            exercise="Bench",
            category="Push",
            weight=105,
            reps=5,
        )
    )

    service = ProgressionService()
    result = service.get_progression_data("Bench", include_upcoming=False)

    assert [p["date"] for p in result["historical"]] == ["2024-01-01", "2024-01-03"]
    assert result["historical"][0]["weight"] == 110
    assert result["upcoming"] == []


def test_progression_data_includes_upcoming_sessions():
    workout_repo = WorkoutRepository()
    upcoming_repo = UpcomingWorkoutRepository()

    workout_repo.create(
        WorkoutCreate(
            date="2024-01-01",
            exercise="Bench",
            category="Push",
            weight=100,
            reps=5,
        )
    )

    upcoming_repo.create(
        UpcomingWorkoutCreate(session=1, exercise="Bench", category="Push", weight=120, reps=3)
    )
    upcoming_repo.create(
        UpcomingWorkoutCreate(session=2, exercise="Bench", category="Push", weight=125, reps=2)
    )

    service = ProgressionService()
    result = service.get_progression_data("Bench", include_upcoming=True)

    assert len(result["upcoming"]) == 2
    assert result["upcoming"][0]["session"] == 1


def test_progression_main_lifts_returns_all_keys():
    service = ProgressionService()
    result = service.get_main_lifts_progression()
    assert set(result.keys()) == {
        "Flat Barbell Bench Press",
        "Barbell Squat",
        "Deadlift",
    }


def test_historical_day_carries_every_set_best_first():
    """A day is a session, not its heaviest moment.

    The leading numbers stay the best set — that is the one point the chart
    plots for the day — and `sets` carries the rest in the order performed.
    """
    workout_repo = WorkoutRepository()
    for order, (weight, reps) in enumerate([(135, 10), (185, 5), (155, 8)], start=1):
        workout_repo.create(
            WorkoutCreate(
                date="2026-07-08",
                exercise="Bench",
                category="Chest",
                weight=weight,
                reps=reps,
                order=order,
            )
        )

    data = ProgressionService().get_progression_data("Bench", include_upcoming=False)
    day = data["historical"][0]

    # 185x5 estimates highest, so it leads.
    assert day["weight"] == 185
    assert [s["weight"] for s in day["sets"]] == [135, 185, 155]
    assert day["estimated_1rm"] == max(s["estimated_1rm"] for s in day["sets"])
