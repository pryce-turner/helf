"""Exercise and category repository for database operations."""


from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.db.models import Category, Exercise
from app.models.exercise import CategoryCreate, ExerciseCreate, ExerciseUpdate
from app.utils.date_helpers import get_current_datetime


# The twelve field-configuration columns (plan 0018). One list, iterated by
# `_serialize`, `create` and `update`, so a fourteenth field cannot be added
# to the schema and forgotten here.
FIELD_CONFIG = (
    "movement_break_enabled",
    "reps_enabled",
    "default_reps",
    "weight_enabled",
    "default_weight_lb",
    "distance_enabled",
    "default_distance",
    "default_distance_unit",
    "time_enabled",
    "default_work_seconds",
    "default_rest_seconds",
    "default_rest_after_seconds",
)

#: Nullable defaults: cleared by an explicit null, told apart from an omitted
#: key by `model_fields_set` the way `rating` is. The boolean flags use the
#: plain `is not None` guard instead — a flag has no third state to clear to.
NULLABLE_DEFAULTS = tuple(
    field for field in FIELD_CONFIG if field.startswith("default_")
)


class ExerciseRepository:
    """Repository for exercise data operations."""

    def _serialize(self, exercise: Exercise) -> dict:
        return {
            "doc_id": exercise.id,
            "name": exercise.name,
            "category": exercise.category.name if exercise.category else None,
            "form": exercise.form,
            "application": exercise.application,
            "rating": exercise.rating,
            **{field: getattr(exercise, field) for field in FIELD_CONFIG},
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

    def get_by_name(self, name: str) -> dict | None:
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
                form=exercise.form,
                application=exercise.application,
                rating=exercise.rating,
                last_used=None,
                use_count=0,
                created_at=now,
                **{field: getattr(exercise, field) for field in FIELD_CONFIG},
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

    def get_movement_breaks(self) -> list[dict]:
        """The movement break pool: movements that need no equipment, with their
        timing defaults.

        A dedicated read rather than a filter over `get_all()`, which carries
        every movement's full `form` and `application` across the wire to a
        phone in an office to pick one name out of it.
        """
        with SessionLocal() as session:
            exercises = session.execute(
                select(Exercise)
                .options(selectinload(Exercise.category))
                .where(Exercise.movement_break_enabled.is_(True))
                .order_by(Exercise.name)
            ).scalars().all()
            return [self._serialize(exercise) for exercise in exercises]

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

    def update(self, exercise_id: int, data: ExerciseUpdate) -> dict | None:
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
            # Two fields now, and they are edited independently: recording
            # what a session taught you about *applying* a movement must not
            # require restating how to perform it (e2b9c4d17a05).
            if data.form is not None:
                exercise.form = data.form if data.form else None
            if data.application is not None:
                exercise.application = data.application if data.application else None
            # `rating: null` means "unrate this", which is indistinguishable
            # from an omitted field by value alone. `model_fields_set` carries
            # what the client actually sent.
            if "rating" in data.model_fields_set:
                exercise.rating = data.rating
            # The field configuration (plan 0018). The flags are plain
            # optionals; the nullable defaults share `rating`'s problem —
            # clearing one back to blank is a real edit. Disabling a group
            # deliberately does **not** clear its defaults: re-enabling must
            # restore the configuration, not a blank one.
            for field in FIELD_CONFIG:
                if field in NULLABLE_DEFAULTS:
                    if field in data.model_fields_set:
                        setattr(exercise, field, getattr(data, field))
                else:
                    value = getattr(data, field)
                    if value is not None:
                        setattr(exercise, field, value)

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

    def get_by_name(self, name: str) -> dict | None:
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
