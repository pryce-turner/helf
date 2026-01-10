"""Exercise and category repository for database operations."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.db.models import Category, Exercise
from app.models.exercise import CategoryCreate, ExerciseCreate, ExerciseUpdate
from app.utils.date_helpers import get_current_datetime


class ExerciseRepository:
    """Repository for exercise data operations."""

    def _serialize(self, exercise: Exercise) -> dict:
        return {
            "doc_id": exercise.id,
            "name": exercise.name,
            "category": exercise.category.name if exercise.category else None,
            "last_used": exercise.last_used,
            "use_count": exercise.use_count,
            "created_at": exercise.created_at,
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

    def get_all(self) -> list[dict]:
        """Get all exercises."""
        with SessionLocal() as session:
            exercises = session.execute(
                select(Exercise).options(selectinload(Exercise.category))
            ).scalars().all()
            return [self._serialize(exercise) for exercise in exercises]

    def get_by_name(self, name: str) -> Optional[dict]:
        """Get an exercise by name."""
        with SessionLocal() as session:
            exercise = session.execute(
                select(Exercise)
                .options(selectinload(Exercise.category))
                .where(Exercise.name == name)
            ).scalar_one_or_none()
            return self._serialize(exercise) if exercise else None

    def get_by_category(self, category: str) -> list[dict]:
        """Get all exercises in a category."""
        with SessionLocal() as session:
            exercises = session.execute(
                select(Exercise)
                .join(Category)
                .options(selectinload(Exercise.category))
                .where(Category.name == category)
                .order_by(Exercise.last_used.desc())
            ).scalars().all()
            return [self._serialize(exercise) for exercise in exercises]

    def create(self, exercise: ExerciseCreate) -> dict:
        """Create a new exercise."""
        with SessionLocal() as session:
            existing = session.execute(
                select(Exercise)
                .options(selectinload(Exercise.category))
                .where(Exercise.name == exercise.name)
            ).scalar_one_or_none()
            if existing:
                return self._serialize(existing)

            category = self._get_or_create_category(session, exercise.category)
            now = get_current_datetime()

            new_exercise = Exercise(
                name=exercise.name,
                category_id=category.id,
                last_used=None,
                use_count=0,
                created_at=now,
            )
            session.add(new_exercise)
            session.commit()
            session.refresh(new_exercise)
            return self._serialize(new_exercise)

    def update_usage(self, name: str, date: str) -> bool:
        """Update exercise usage statistics."""
        with SessionLocal() as session:
            exercise = session.execute(
                select(Exercise).where(Exercise.name == name)
            ).scalar_one_or_none()
            if not exercise:
                return False

            exercise.last_used = date
            exercise.use_count = (exercise.use_count or 0) + 1
            session.commit()
            return True

    def get_recent(self, limit: int = 10) -> list[dict]:
        """Get recently used exercises."""
        with SessionLocal() as session:
            exercises = session.execute(
                select(Exercise)
                .options(selectinload(Exercise.category))
                .where(Exercise.last_used.is_not(None))
                .order_by(Exercise.last_used.desc())
                .limit(limit)
            ).scalars().all()
            return [self._serialize(exercise) for exercise in exercises]

    def update(self, exercise_id: int, data: ExerciseUpdate) -> Optional[dict]:
        """Update an exercise."""
        with SessionLocal() as session:
            exercise = session.execute(
                select(Exercise)
                .options(selectinload(Exercise.category))
                .where(Exercise.id == exercise_id)
            ).scalar_one_or_none()
            if not exercise:
                return None

            if data.name is not None:
                exercise.name = data.name
            if data.category is not None:
                category = self._get_or_create_category(session, data.category)
                exercise.category_id = category.id

            session.commit()
            session.refresh(exercise)
            return self._serialize(exercise)

    def delete(self, exercise_id: int) -> bool:
        """Delete an exercise."""
        with SessionLocal() as session:
            exercise = session.execute(
                select(Exercise).where(Exercise.id == exercise_id)
            ).scalar_one_or_none()
            if not exercise:
                return False

            session.delete(exercise)
            session.commit()
            return True


class CategoryRepository:
    """Repository for category data operations."""

    def _serialize(self, category: Category) -> dict:
        return {
            "doc_id": category.id,
            "name": category.name,
            "created_at": category.created_at,
        }

    def get_all(self) -> list[dict]:
        """Get all categories."""
        with SessionLocal() as session:
            categories = session.execute(
                select(Category).order_by(Category.name.asc())
            ).scalars().all()
            return [self._serialize(category) for category in categories]

    def get_by_name(self, name: str) -> Optional[dict]:
        """Get a category by name."""
        with SessionLocal() as session:
            category = session.execute(
                select(Category).where(Category.name == name)
            ).scalar_one_or_none()
            return self._serialize(category) if category else None

    def create(self, category: CategoryCreate) -> dict:
        """Create a new category."""
        with SessionLocal() as session:
            existing = session.execute(
                select(Category).where(Category.name == category.name)
            ).scalar_one_or_none()
            if existing:
                return self._serialize(existing)

            now = get_current_datetime()
            new_category = Category(
                name=category.name,
                created_at=now,
            )
            session.add(new_category)
            session.commit()
            session.refresh(new_category)
            return self._serialize(new_category)
