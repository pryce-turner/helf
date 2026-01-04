#!/usr/bin/env python3
"""Generate test workout data for January 2026."""

import json
from datetime import datetime, timedelta
from pathlib import Path

# Categories and exercises
CATEGORIES = {
    "Chest": ["Bench Press", "Incline Bench Press", "Dumbbell Flyes", "Push-ups"],
    "Back": ["Deadlift", "Bent Over Row", "Pull-ups", "Lat Pulldown"],
    "Legs": ["Squat", "Romanian Deadlift", "Leg Press", "Lunges", "Leg Curl"],
    "Shoulders": ["Overhead Press", "Lateral Raise", "Face Pulls", "Arnold Press"],
    "Arms": ["Barbell Curl", "Tricep Dips", "Hammer Curl", "Skull Crushers"],
    "Core": ["Plank", "Ab Wheel", "Hanging Leg Raise", "Cable Crunch"],
    "Cardio": ["Running", "Cycling", "Rowing"]
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
    }
}

def generate_database():
    """Generate TinyDB database with test data."""

    db_data = {
        "_default": {},
        "categories": {},
        "exercises": {},
        "workouts": {},
        "upcoming_workouts": {},
        "body_composition": {}
    }

    # Generate categories
    category_id = 1
    for category_name in CATEGORIES.keys():
        db_data["categories"][str(category_id)] = {
            "name": category_name,
            "created_at": datetime(2025, 12, 1, 10, 0, 0).isoformat()
        }
        category_id += 1

    # Generate exercises
    exercise_id = 1
    for category_name, exercises in CATEGORIES.items():
        for exercise_name in exercises:
            db_data["exercises"][str(exercise_id)] = {
                "name": exercise_name,
                "category": category_name,
                "last_used": None,
                "use_count": 0,
                "created_at": datetime(2025, 12, 1, 10, 0, 0).isoformat()
            }
            exercise_id += 1

    # Generate workouts for January 2026
    workout_id = 1
    start_date = datetime(2026, 1, 1)

    # 3 workouts per week (Monday, Wednesday, Friday) for January
    workout_days = []
    current_date = start_date
    while current_date.month == 1:
        if current_date.weekday() in [0, 2, 4]:  # Mon, Wed, Fri
            workout_days.append(current_date)
        current_date += timedelta(days=1)

    # Rotate through workout splits
    split_rotation = ["Push", "Pull", "Legs"]

    for day_idx, workout_date in enumerate(workout_days):
        split_type = split_rotation[day_idx % 3]
        workout_template = WORKOUT_SPLITS[split_type]

        # Add slight progressive overload (0-5 lbs per week)
        week_number = day_idx // 3
        progression = week_number * 2.5

        order = 0
        for exercise_name, base_stats in workout_template.items():
            # Find category for this exercise
            category = None
            for cat, exercises in CATEGORIES.items():
                if exercise_name in exercises:
                    category = cat
                    break

            # Determine number of sets
            num_sets = base_stats.get("sets", 3)

            # Create multiple entries for each set
            for set_num in range(num_sets):
                weight = base_stats["weight"] + progression if base_stats["weight"] > 0 else 0
                reps = base_stats["reps"]

                # Add variation to sets (sometimes hit AMRAP on last set)
                if set_num == num_sets - 1 and reps <= 8:
                    # Last set might be AMRAP
                    if day_idx % 2 == 0:
                        reps = f"{reps}+"

                workout_entry = {
                    "date": workout_date.strftime("%Y-%m-%d"),
                    "exercise": exercise_name,
                    "category": category,
                    "weight": weight if weight > 0 else None,
                    "weight_unit": "lbs",
                    "reps": reps,
                    "distance": None,
                    "distance_unit": None,
                    "time": None,
                    "comment": f"Week {week_number + 1}" if set_num == 0 else None,
                    "order": order,
                    "created_at": workout_date.replace(hour=8, minute=0, second=0).isoformat(),
                    "updated_at": workout_date.replace(hour=8, minute=0, second=0).isoformat()
                }

                db_data["workouts"][str(workout_id)] = workout_entry
                workout_id += 1
                order += 1

    # Add some cardio workouts
    cardio_dates = [datetime(2026, 1, 4), datetime(2026, 1, 11), datetime(2026, 1, 18), datetime(2026, 1, 25)]
    for cardio_date in cardio_dates:
        db_data["workouts"][str(workout_id)] = {
            "date": cardio_date.strftime("%Y-%m-%d"),
            "exercise": "Running",
            "category": "Cardio",
            "weight": None,
            "weight_unit": "lbs",
            "reps": None,
            "distance": 5.0,
            "distance_unit": "km",
            "time": "30:00",
            "comment": "Easy recovery run",
            "order": 0,
            "created_at": cardio_date.replace(hour=7, minute=0, second=0).isoformat(),
            "updated_at": cardio_date.replace(hour=7, minute=0, second=0).isoformat()
        }
        workout_id += 1

    return db_data

def main():
    """Generate and save test database."""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)

    db_path = data_dir / "helf.json"

    print(f"Generating test data...")
    db_data = generate_database()

    # Count entries
    num_categories = len(db_data["categories"])
    num_exercises = len(db_data["exercises"])
    num_workouts = len(db_data["workouts"])

    print(f"Generated:")
    print(f"  - {num_categories} categories")
    print(f"  - {num_exercises} exercises")
    print(f"  - {num_workouts} workout entries")

    # Write to file
    with open(db_path, 'w') as f:
        json.dump(db_data, f, indent=2)

    print(f"\nDatabase written to: {db_path}")
    print("✓ Test data generation complete!")

if __name__ == "__main__":
    main()
