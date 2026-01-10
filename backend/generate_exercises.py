#!/usr/bin/env python3
"""Seed exercise library with exercises from workout presets."""

from pathlib import Path
import sys

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal, init_db
from app.db.models import Category, Exercise

# All exercises from presets organized by category
# These match the exercises used in:
# - wendler_531.liftoscript
# - stronglifts_5x5.liftoscript
PRESET_EXERCISES = {
    "Legs": [
        "Barbell Squat",
        "Front Squat",
        "Bulgarian Split Squat",
    ],
    "Push": [
        "Flat Barbell Bench Press",
        "Incline Dumbbell Press",
        "Overhead Press",
        "Parallel Bar Triceps Dip",
    ],
    "Pull": [
        "Deadlift",
        "Pull-ups",
        "Dumbbell Row",
        "Barbell Row",
    ],
    "Core": [
        "Decline Crunch",
        "Landmines",
        "Cable side bend",
    ],
}


def seed_exercises() -> dict[str, int]:
    """Seed exercises from presets into the database.

    Returns a dict with counts of created categories and exercises.
    Only creates exercises that don't already exist.
    """
    init_db()

    created_categories = 0
    created_exercises = 0

    with SessionLocal() as session:
        for category_name, exercises in PRESET_EXERCISES.items():
            # Get or create category
            category = session.query(Category).filter(Category.name == category_name).first()
            if not category:
                category = Category(name=category_name)
                session.add(category)
                session.flush()
                created_categories += 1

            # Create exercises that don't exist
            for exercise_name in exercises:
                existing = session.query(Exercise).filter(Exercise.name == exercise_name).first()
                if not existing:
                    exercise = Exercise(
                        name=exercise_name,
                        category_id=category.id,
                        last_used=None,
                        use_count=0,
                    )
                    session.add(exercise)
                    created_exercises += 1

        session.commit()

    return {
        "categories_created": created_categories,
        "exercises_created": created_exercises,
    }


def main():
    """Seed exercises and print results."""
    print("Seeding exercises from presets...")
    result = seed_exercises()
    print(f"\nCreated {result['categories_created']} categories")
    print(f"Created {result['exercises_created']} exercises")
    print("Done!")


if __name__ == "__main__":
    main()
