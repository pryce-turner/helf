#!/usr/bin/env python3
"""Generate test workout data for January 2026 (SQLite)."""

from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings
from app.database import SessionLocal, init_db
from app.db.models import Category, Exercise, Workout

# Categories and exercises
CATEGORIES = {
    "Chest": ["Bench Press", "Incline Bench Press", "Dumbbell Flyes", "Push-ups"],
    "Back": ["Deadlift", "Bent Over Row", "Pull-ups", "Lat Pulldown", "Dumbbell Row"],
    "Legs": [
        "Squat",
        "Romanian Deadlift",
        "Leg Press",
        "Lunges",
        "Leg Curl",
        # Wendler exercises
        "Barbell Squat",
        "Front Squat",
        "Bulgarian Split Squat",
    ],
    "Shoulders": ["Overhead Press", "Lateral Raise", "Face Pulls", "Arnold Press"],
    "Arms": ["Barbell Curl", "Tricep Dips", "Hammer Curl", "Skull Crushers", "Parallel Bar Triceps Dip"],
    "Core": ["Plank", "Ab Wheel", "Hanging Leg Raise", "Cable Crunch", "Decline Crunch", "Landmines", "Cable side bend"],
    "Cardio": ["Running", "Cycling", "Rowing"],
    # Wendler Push/Pull categories
    "Push": ["Flat Barbell Bench Press", "Incline Dumbbell Press"],
    "Pull": ["Pull Up"],
}

# Workout templates for different days
WORKOUT_SPLITS = {
    "Push": {
        "Bench Press": {"weight": 185, "reps": 5, "sets": 5},
        "Incline Bench Press": {"weight": 155, "reps": 8, "sets": 4},
        "Overhead Press": {"weight": 115, "reps": 5, "sets": 5},
        "Lateral Raise": {"weight": 25, "reps": 12, "sets": 3},
        "Tricep Dips": {"weight": 45, "reps": 10, "sets": 3},
    },
    "Pull": {
        "Deadlift": {"weight": 275, "reps": 5, "sets": 3},
        "Pull-ups": {"weight": 0, "reps": 8, "sets": 4},
        "Bent Over Row": {"weight": 165, "reps": 8, "sets": 4},
        "Face Pulls": {"weight": 60, "reps": 15, "sets": 3},
        "Barbell Curl": {"weight": 75, "reps": 10, "sets": 3},
    },
    "Legs": {
        "Squat": {"weight": 225, "reps": 5, "sets": 5},
        "Romanian Deadlift": {"weight": 185, "reps": 8, "sets": 4},
        "Leg Press": {"weight": 315, "reps": 12, "sets": 3},
        "Leg Curl": {"weight": 100, "reps": 12, "sets": 3},
        "Plank": {"weight": 0, "reps": 60, "sets": 3},
    },
}


def generate_database():
    """Generate SQLite database with test data."""
    init_db()

    with SessionLocal() as session:
        # Clear existing data
        session.query(Workout).delete()
        session.query(Exercise).delete()
        session.query(Category).delete()
        session.commit()

        # Generate categories
        category_map: dict[str, Category] = {}
        created_at = datetime(2025, 12, 1, 10, 0, 0)
        for category_name in CATEGORIES.keys():
            category = Category(name=category_name, created_at=created_at)
            session.add(category)
            category_map[category_name] = category
        session.flush()

        # Generate exercises
        exercise_map: dict[str, Exercise] = {}
        for category_name, exercises in CATEGORIES.items():
            for exercise_name in exercises:
                exercise = Exercise(
                    name=exercise_name,
                    category_id=category_map[category_name].id,
                    last_used=None,
                    use_count=0,
                    created_at=created_at,
                )
                session.add(exercise)
                exercise_map[exercise_name] = exercise
        session.flush()

        # Generate workouts for January 2026
        start_date = datetime(2026, 1, 1)

        # 3 workouts per week (Monday, Wednesday, Friday) for January
        workout_days = []
        current_date = start_date
        while current_date.month == 1:
            if current_date.weekday() in [0, 2, 4]:
                workout_days.append(current_date)
            current_date += timedelta(days=1)

        split_rotation = ["Push", "Pull", "Legs"]

        for day_idx, workout_date in enumerate(workout_days):
            split_type = split_rotation[day_idx % 3]
            workout_template = WORKOUT_SPLITS[split_type]

            week_number = day_idx // 3
            progression = week_number * 2.5

            order = 0
            for exercise_name, base_stats in workout_template.items():
                category_name = None
                for cat, exercises in CATEGORIES.items():
                    if exercise_name in exercises:
                        category_name = cat
                        break

                num_sets = base_stats.get("sets", 3)

                for set_num in range(num_sets):
                    weight = base_stats["weight"] + progression if base_stats["weight"] > 0 else 0
                    reps = base_stats["reps"]

                    workout_entry = Workout(
                        date=workout_date.strftime("%Y-%m-%d"),
                        exercise_id=exercise_map[exercise_name].id,
                        category_id=category_map[category_name].id,
                        weight=weight if weight > 0 else None,
                        weight_unit="lbs",
                        reps=reps,
                        distance=None,
                        distance_unit=None,
                        time=None,
                        comment=f"Week {week_number + 1}" if set_num == 0 else None,
                        order=order,
                        created_at=workout_date.replace(hour=8, minute=0, second=0),
                        updated_at=workout_date.replace(hour=8, minute=0, second=0),
                    )
                    session.add(workout_entry)
                    order += 1

        # Add some cardio workouts
        cardio_dates = [
            datetime(2026, 1, 4),
            datetime(2026, 1, 11),
            datetime(2026, 1, 18),
            datetime(2026, 1, 25),
        ]
        for cardio_date in cardio_dates:
            workout_entry = Workout(
                date=cardio_date.strftime("%Y-%m-%d"),
                exercise_id=exercise_map["Running"].id,
                category_id=category_map["Cardio"].id,
                weight=None,
                weight_unit="lbs",
                reps=None,
                distance=5.0,
                distance_unit="km",
                time="30:00",
                comment="Easy recovery run",
                order=0,
                created_at=cardio_date.replace(hour=7, minute=0, second=0),
                updated_at=cardio_date.replace(hour=7, minute=0, second=0),
            )
            session.add(workout_entry)

        session.commit()


def main():
    """Generate and save test database."""
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "helf.db"

    print("Generating test data...")
    generate_database()

    print("\nDatabase written to:", db_path)
    print("✓ Test data generation complete!")


if __name__ == "__main__":
    main()
