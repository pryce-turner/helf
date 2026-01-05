#!/usr/bin/env python3
"""Migration script: TinyDB JSON -> SQLite (SQLAlchemy)."""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.database import SessionLocal, init_db
from app.db.models import BodyComposition, Category, Exercise, UpcomingWorkout, Workout

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PACIFIC_TZ)
    return dt


def ensure_category(session, name: str, created_at: datetime | None, cache: dict[str, Category]) -> Category:
    category = cache.get(name)
    if category:
        return category

    category = session.query(Category).filter(Category.name == name).one_or_none()
    if category:
        cache[name] = category
        return category

    category = Category(
        name=name,
        created_at=created_at or datetime.now(PACIFIC_TZ),
    )
    session.add(category)
    session.flush()
    cache[name] = category
    return category


def ensure_exercise(
    session,
    name: str,
    category: Category,
    created_at: datetime | None,
    last_used: str | None,
    use_count: int | None,
    cache: dict[str, Exercise],
) -> Exercise:
    exercise = cache.get(name)
    if exercise:
        return exercise

    exercise = session.query(Exercise).filter(Exercise.name == name).one_or_none()
    if exercise:
        cache[name] = exercise
        return exercise

    exercise = Exercise(
        name=name,
        category_id=category.id,
        last_used=last_used,
        use_count=use_count or 0,
        created_at=created_at or datetime.now(PACIFIC_TZ),
    )
    session.add(exercise)
    session.flush()
    cache[name] = exercise
    return exercise


def main():
    print("=" * 60)
    print("TinyDB JSON to SQLite Migration")
    print("=" * 60)

    json_path = Path(__file__).parent.parent.parent / "data" / "helf.json"
    if not json_path.exists():
        print(f"TinyDB JSON not found at {json_path}")
        sys.exit(1)

    db_path = settings.db_path

    if db_path.exists():
        if "--force" in sys.argv:
            print(f"\nDatabase {db_path} exists. Overwriting (--force)...")
            db_path.unlink()
        else:
            response = input(f"\nDatabase {db_path} already exists. Overwrite? (y/N): ")
            if response.lower() != "y":
                print("Migration cancelled.")
                return
            db_path.unlink()

    init_db()

    data = json.loads(json_path.read_text())

    categories_table = data.get("categories", {})
    exercises_table = data.get("exercises", {})
    workouts_table = data.get("workouts", {})
    upcoming_table = data.get("upcoming_workouts", {})
    body_comp_table = data.get("body_composition", {})

    counts = {
        "categories": 0,
        "exercises": 0,
        "workouts": 0,
        "upcoming_workouts": 0,
        "body_composition": 0,
    }

    with SessionLocal() as session:
        category_cache: dict[str, Category] = {}
        exercise_cache: dict[str, Exercise] = {}

        # Categories
        for row in categories_table.values():
            name = row.get("name")
            if not name:
                continue
            category = ensure_category(
                session,
                name,
                parse_datetime(row.get("created_at")),
                category_cache,
            )
            if category:
                counts["categories"] += 1

        # Exercises
        for row in exercises_table.values():
            name = row.get("name")
            category_name = row.get("category")
            if not name or not category_name:
                continue
            category = ensure_category(
                session,
                category_name,
                None,
                category_cache,
            )
            exercise = ensure_exercise(
                session,
                name,
                category,
                parse_datetime(row.get("created_at")),
                row.get("last_used"),
                row.get("use_count"),
                exercise_cache,
            )
            if exercise:
                counts["exercises"] += 1

        # Workouts
        for row in workouts_table.values():
            category_name = row.get("category")
            exercise_name = row.get("exercise")
            if not category_name or not exercise_name:
                continue

            category = ensure_category(
                session,
                category_name,
                None,
                category_cache,
            )
            exercise = ensure_exercise(
                session,
                exercise_name,
                category,
                None,
                None,
                None,
                exercise_cache,
            )

            reps = row.get("reps")
            if reps is not None and not isinstance(reps, str):
                reps = str(reps)

            order_value = row.get("order")
            if order_value is None:
                order_value = 1

            workout = Workout(
                date=row.get("date"),
                exercise_id=exercise.id,
                category_id=category.id,
                weight=row.get("weight"),
                weight_unit=row.get("weight_unit") or "lbs",
                reps=reps,
                distance=row.get("distance"),
                distance_unit=row.get("distance_unit"),
                time=row.get("time"),
                comment=row.get("comment"),
                order=order_value,
                created_at=parse_datetime(row.get("created_at")) or datetime.now(PACIFIC_TZ),
                updated_at=parse_datetime(row.get("updated_at")) or datetime.now(PACIFIC_TZ),
                completed_at=parse_datetime(row.get("completed_at")),
            )
            session.add(workout)
            counts["workouts"] += 1

        # Upcoming workouts
        for row in upcoming_table.values():
            category_name = row.get("category")
            exercise_name = row.get("exercise")
            if not category_name or not exercise_name:
                continue

            category = ensure_category(
                session,
                category_name,
                None,
                category_cache,
            )
            exercise = ensure_exercise(
                session,
                exercise_name,
                category,
                None,
                None,
                None,
                exercise_cache,
            )

            reps = row.get("reps")
            if reps is not None and not isinstance(reps, str):
                reps = str(reps)

            workout = UpcomingWorkout(
                session=row.get("session") or 0,
                exercise_id=exercise.id,
                category_id=category.id,
                weight=row.get("weight"),
                weight_unit=row.get("weight_unit") or "lbs",
                reps=reps,
                distance=row.get("distance"),
                distance_unit=row.get("distance_unit"),
                time=row.get("time"),
                comment=row.get("comment"),
                created_at=parse_datetime(row.get("created_at")) or datetime.now(PACIFIC_TZ),
            )
            session.add(workout)
            counts["upcoming_workouts"] += 1

        # Body composition
        for row in body_comp_table.values():
            timestamp = parse_datetime(row.get("timestamp"))
            weight = row.get("weight")
            if not timestamp or weight is None:
                continue

            measurement = BodyComposition(
                timestamp=timestamp,
                date=row.get("date"),
                weight=weight,
                weight_unit=row.get("weight_unit") or "kg",
                body_fat_pct=row.get("body_fat_pct"),
                muscle_mass=row.get("muscle_mass"),
                bmi=row.get("bmi"),
                water_pct=row.get("water_pct"),
                bone_mass=row.get("bone_mass"),
                visceral_fat=row.get("visceral_fat"),
                metabolic_age=row.get("metabolic_age"),
                protein_pct=row.get("protein_pct"),
                created_at=parse_datetime(row.get("created_at")) or timestamp,
            )
            session.add(measurement)
            counts["body_composition"] += 1

        session.commit()

    print()
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Categories:         {counts['categories']:>6}")
    print(f"Exercises:          {counts['exercises']:>6}")
    print(f"Workouts:           {counts['workouts']:>6}")
    print(f"Upcoming workouts:  {counts['upcoming_workouts']:>6}")
    print(f"Body composition:   {counts['body_composition']:>6}")
    print("=" * 60)
    print(f"Migration complete! Database saved to {db_path}")


if __name__ == "__main__":
    main()
