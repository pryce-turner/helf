"""Workout repository for database operations."""


from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.db.models import Category, Exercise, Workout
from app.models.workout import WorkoutCreate, WorkoutUpdate
from app.utils.date_helpers import get_current_datetime
from app.utils.units import CANONICAL_WEIGHT_UNIT


class WorkoutRepository:
    """Repository for workout data operations."""

    def _serialize(self, workout: Workout) -> dict:
        return {
            "doc_id": workout.id,
            "date": workout.date,
            "exercise": workout.exercise.name if workout.exercise else None,
            "category": workout.category.name if workout.category else None,
            "weight": workout.weight,
            "weight_unit": CANONICAL_WEIGHT_UNIT,
            "reps": workout.reps,
            "distance": workout.distance,
            "distance_unit": workout.distance_unit,
            "time": workout.time,
            "comment": workout.comment,
            "order": workout.order,
            "created_at": workout.created_at,
            "updated_at": workout.updated_at,
            "completed_at": workout.completed_at,
            "is_mobility": bool(workout.is_mobility),
        }

    def _get_or_create_category(self, session, name: str) -> Category:
        category = session.execute(
            select(Category).where(Category.name == name)
        ).scalar_one_or_none()
        if category:
            return category

        category = Category(
            name=name,
            created_at=get_current_datetime(),
        )
        session.add(category)
        session.flush()
        return category

    def _get_or_create_exercise(self, session, name: str, category: Category) -> Exercise:
        exercise = session.execute(
            select(Exercise).where(Exercise.name == name)
        ).scalar_one_or_none()
        if exercise:
            return exercise

        exercise = Exercise(
            name=name,
            category_id=category.id,
            last_used=None,
            use_count=0,
            created_at=get_current_datetime(),
        )
        session.add(exercise)
        session.flush()
        return exercise

    def get_all(self, skip: int = 0, limit: int = 100) -> list[dict]:
        """Get all workouts with pagination."""
        with SessionLocal() as session:
            workouts = session.execute(
                select(Workout)
                .options(selectinload(Workout.exercise), selectinload(Workout.category))
                .order_by(Workout.date.desc(), Workout.order.desc())
                .offset(skip)
                .limit(limit)
            ).scalars().all()
            return [self._serialize(workout) for workout in workouts]

    def get_by_id(self, doc_id: int) -> dict | None:
        """Get a workout by ID."""
        with SessionLocal() as session:
            workout = session.execute(
                select(Workout)
                .options(selectinload(Workout.exercise), selectinload(Workout.category))
                .where(Workout.id == doc_id)
            ).scalar_one_or_none()
            return self._serialize(workout) if workout else None

    def get_by_date(self, date: str) -> list[dict]:
        """Get all workouts for a specific date, sorted by order."""
        with SessionLocal() as session:
            workouts = session.execute(
                select(Workout)
                .options(selectinload(Workout.exercise), selectinload(Workout.category))
                .where(Workout.date == date)
                .order_by(Workout.order.asc())
            ).scalars().all()
            return [self._serialize(workout) for workout in workouts]

    def create(self, workout: WorkoutCreate) -> dict:
        """Create a new workout."""
        now = get_current_datetime()
        workout_dict = workout.model_dump(exclude_none=False)

        with SessionLocal() as session:
            category = self._get_or_create_category(session, workout_dict["category"])
            exercise = self._get_or_create_exercise(session, workout_dict["exercise"], category)

            if workout_dict.get("order") is None:
                count = session.execute(
                    select(func.count()).select_from(Workout).where(Workout.date == workout.date)
                ).scalar_one()
                workout_dict["order"] = count + 1

            order_value = workout_dict.get("order")
            if order_value is None:
                order_value = 1

            new_workout = Workout(
                date=workout_dict["date"],
                exercise_id=exercise.id,
                category_id=category.id,
                weight=workout_dict.get("weight"),
                reps=workout_dict.get("reps"),
                distance=workout_dict.get("distance"),
                distance_unit=workout_dict.get("distance_unit"),
                time=workout_dict.get("time"),
                comment=workout_dict.get("comment"),
                order=order_value,
                created_at=now,
                updated_at=now,
                completed_at=workout_dict.get("completed_at"),
                is_mobility=bool(workout_dict.get("is_mobility")),
            )
            session.add(new_workout)
            session.commit()
            session.refresh(new_workout)
            session.refresh(exercise)
            session.refresh(category)
            return self._serialize(new_workout)

    def update(self, doc_id: int, workout: WorkoutUpdate) -> dict | None:
        """Update an existing workout."""
        workout_dict = workout.model_dump(exclude_none=False)

        with SessionLocal() as session:
            existing = session.get(Workout, doc_id)
            if not existing:
                return None

            category = self._get_or_create_category(session, workout_dict["category"])
            exercise = self._get_or_create_exercise(session, workout_dict["exercise"], category)

            existing.date = workout_dict["date"]
            existing.exercise_id = exercise.id
            existing.category_id = category.id
            existing.weight = workout_dict.get("weight")
            existing.reps = workout_dict.get("reps")
            existing.distance = workout_dict.get("distance")
            existing.distance_unit = workout_dict.get("distance_unit")
            existing.time = workout_dict.get("time")
            existing.comment = workout_dict.get("comment")
            if workout_dict.get("order") is not None:
                existing.order = workout_dict.get("order")
            existing.completed_at = workout_dict.get("completed_at")
            # Sticky unless explicitly sent, distinguished by `model_fields_set`
            # the way `ExerciseUpdate.rating` is. Every other field here is a
            # full replace, but this one defaults to False, so a PUT that only
            # meant to change a comment would silently unflag the set - and
            # editing a comment to add feedback is precisely what happens to a
            # mobility set after it is run. The flag would disappear at the
            # moment the loop depends on it.
            if "is_mobility" in workout.model_fields_set:
                existing.is_mobility = bool(workout_dict.get("is_mobility"))
            existing.updated_at = get_current_datetime()

            session.commit()
            session.refresh(existing)
            return self._serialize(existing)

    def delete(self, doc_id: int) -> bool:
        """Delete a workout."""
        with SessionLocal() as session:
            workout = session.get(Workout, doc_id)
            if not workout:
                return False
            session.delete(workout)
            session.commit()
            return True

    def toggle_complete(self, doc_id: int, completed: bool) -> dict | None:
        """Mark a workout as complete or incomplete."""
        with SessionLocal() as session:
            workout = session.get(Workout, doc_id)
            if not workout:
                return None

            now = get_current_datetime()
            workout.completed_at = now if completed else None
            workout.updated_at = now
            session.commit()
            session.refresh(workout)
            return self._serialize(workout)

    def reorder(self, doc_id: int, date: str, direction: str) -> bool:
        """Reorder a workout within its date."""
        with SessionLocal() as session:
            workouts = session.execute(
                select(Workout)
                .where(Workout.date == date)
                .order_by(Workout.order.asc())
            ).scalars().all()

            workout_index = None
            for i, w in enumerate(workouts):
                if w.id == doc_id:
                    workout_index = i
                    break

            if workout_index is None:
                return False

            if direction == "up" and workout_index == 0:
                return False
            if direction == "down" and workout_index == len(workouts) - 1:
                return False

            swap_index = workout_index - 1 if direction == "up" else workout_index + 1

            workouts[workout_index].order, workouts[swap_index].order = (
                workouts[swap_index].order,
                workouts[workout_index].order,
            )
            session.commit()
            return True

    def bulk_reorder(self, workout_ids: list[int]) -> bool:
        """Bulk reorder workouts by setting order based on position in list."""
        if not workout_ids:
            return False

        with SessionLocal() as session:
            workouts = session.execute(
                select(Workout).where(Workout.id.in_(workout_ids))
            ).scalars().all()

            workout_map = {workout.id: workout for workout in workouts}
            for order, doc_id in enumerate(workout_ids, start=1):
                if doc_id in workout_map:
                    workout_map[doc_id].order = order

            session.commit()
            return True

    def move_to_date(self, source_date: str, target_date: str) -> int:
        """Move all workouts from one date to another."""
        with SessionLocal() as session:
            source_workouts = session.execute(
                select(Workout).where(Workout.date == source_date).order_by(Workout.order.asc())
            ).scalars().all()
            if not source_workouts:
                return 0

            target_count = session.execute(
                select(func.count()).select_from(Workout).where(Workout.date == target_date)
            ).scalar_one()
            starting_order = target_count + 1

            now = get_current_datetime()
            for i, workout in enumerate(source_workouts):
                workout.date = target_date
                workout.order = starting_order + i
                workout.updated_at = now

            session.commit()
            return len(source_workouts)

    def copy_to_date(self, source_date: str, target_date: str) -> int:
        """Copy all workouts from one date to another."""
        with SessionLocal() as session:
            # Get source workouts
            source_workouts = session.execute(
                select(Workout).where(Workout.date == source_date).order_by(Workout.order.asc())
            ).scalars().all()

            if not source_workouts:
                return 0

            # Get target date's max order
            target_count = session.execute(
                select(func.count()).select_from(Workout).where(Workout.date == target_date)
            ).scalar_one()
            starting_order = target_count + 1

            # Create copies
            now = get_current_datetime()
            for i, source_workout in enumerate(source_workouts):
                new_workout = Workout(
                    date=target_date,
                    exercise=source_workout.exercise,
                    category=source_workout.category,
                    weight=source_workout.weight,
                    reps=source_workout.reps,
                    distance=source_workout.distance,
                    distance_unit=source_workout.distance_unit,
                    time=source_workout.time,
                    comment=source_workout.comment,
                    order=starting_order + i,
                    created_at=now,
                    updated_at=now,
                    completed_at=None,  # Reset completion status for copies
                    # Copied sets keep their intent: a mobility session
                    # copied to another date is still mobility work.
                    is_mobility=source_workout.is_mobility,
                )
                session.add(new_workout)

            session.commit()
            return len(source_workouts)

    def get_workout_counts_by_date(self, year: int, month: int) -> dict[str, int]:
        """Get workout counts grouped by date for a specific month."""
        pattern = f"{year}-{month:02d}-%"

        with SessionLocal() as session:
            rows = session.execute(
                select(Workout.date, func.count())
                .where(Workout.date.like(pattern))
                .group_by(Workout.date)
            ).all()

            return {date: count for date, count in rows}

    def get_by_exercise(self, exercise: str) -> list[dict]:
        """Get all workouts for a specific exercise."""
        with SessionLocal() as session:
            workouts = session.execute(
                select(Workout)
                .join(Exercise)
                .options(selectinload(Workout.exercise), selectinload(Workout.category))
                .where(Exercise.name == exercise)
                # `order` as the tiebreak so a day's sets come back in the
                # sequence they were performed, which is what the progression
                # history lists under each date.
                .order_by(Workout.date.asc(), Workout.order.asc())
            ).scalars().all()
            return [self._serialize(workout) for workout in workouts]
