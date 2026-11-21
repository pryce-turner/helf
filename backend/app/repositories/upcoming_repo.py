"""Upcoming workout repository for database operations."""


from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.db.models import Category, Exercise, UpcomingWorkout
from app.models.upcoming import UpcomingWorkoutCreate
from app.utils.date_helpers import get_current_datetime
from app.utils.units import CANONICAL_WEIGHT_UNIT


class UpcomingWorkoutRepository:
    """Repository for upcoming workout data operations.

    The queue is one program (9c4e7b21f806): nothing here is scoped by author
    any more, because the `kind` split that made scoping load-bearing is gone.
    The Liftoscript generator's `delete_all` now really does clear the board —
    the routes layer deletes the `mobility_plan` rows alongside — and the
    frontend warns before confirming.
    """

    def _serialize(self, workout: UpcomingWorkout) -> dict:
        return {
            "doc_id": workout.id,
            "session": workout.session,
            "is_mobility": workout.is_mobility,
            "exercise": workout.exercise.name if workout.exercise else None,
            "category": workout.category.name if workout.category else None,
            "weight": workout.weight,
            "weight_unit": CANONICAL_WEIGHT_UNIT,
            "reps": workout.reps,
            "distance": workout.distance,
            "distance_unit": workout.distance_unit,
            "time": workout.time,
            "comment": workout.comment,
            "created_at": workout.created_at,
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

    def _get_or_create_exercise(
        self, session, name: str, category: Category
    ) -> Exercise:
        """Resolve a movement by name, creating it if it is new.

        Nothing about mobility is recorded here. A movement is not mobility
        work or lifting work; the *set* is (d7e4f2a91b83), and the planned row
        already knows which through `is_mobility`. A good morning prescribed as
        a loaded stretch and the same good morning pulled heavy are one
        exercise row and two different sets.
        """
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

    def get_all(self) -> list[dict]:
        """Get all upcoming workouts, sorted by session."""
        with SessionLocal() as session:
            workouts = (
                session.execute(
                    select(UpcomingWorkout)
                    .options(
                        selectinload(UpcomingWorkout.exercise),
                        selectinload(UpcomingWorkout.category),
                    )
                    .order_by(UpcomingWorkout.session.asc(), UpcomingWorkout.id.asc())
                )
                .scalars()
                .all()
            )
            return [self._serialize(workout) for workout in workouts]

    def get_by_session(self, session_id: int) -> list[dict]:
        """Get all workouts for a specific session.

        Ordered by `id`, which is insertion order. The table has no `order`
        column, so this is the prescribed order of the routine — the author
        writes the items in the sequence they are to be performed and that
        sequence is carried by nothing else.
        """
        with SessionLocal() as session:
            workouts = (
                session.execute(
                    select(UpcomingWorkout)
                    .options(
                        selectinload(UpcomingWorkout.exercise),
                        selectinload(UpcomingWorkout.category),
                    )
                    .where(UpcomingWorkout.session == session_id)
                    .order_by(UpcomingWorkout.id.asc())
                )
                .scalars()
                .all()
            )
            return [self._serialize(workout) for workout in workouts]

    def get_lowest_session(self) -> int | None:
        """Get the lowest session number."""
        with SessionLocal() as session:
            lowest = session.execute(
                select(UpcomingWorkout.session)
                .order_by(UpcomingWorkout.session.asc())
                .limit(1)
            ).scalar_one_or_none()
            return lowest

    def create(self, workout: UpcomingWorkoutCreate) -> dict:
        """Create a new upcoming workout."""
        workout_dict = workout.model_dump(exclude_none=False)

        with SessionLocal() as session:
            category = self._get_or_create_category(session, workout_dict["category"])
            exercise = self._get_or_create_exercise(
                session, workout_dict["exercise"], category
            )

            new_workout = UpcomingWorkout(
                session=workout_dict["session"],
                is_mobility=workout_dict.get("is_mobility") or False,
                exercise_id=exercise.id,
                category_id=category.id,
                weight=workout_dict.get("weight"),
                reps=workout_dict.get("reps"),
                distance=workout_dict.get("distance"),
                distance_unit=workout_dict.get("distance_unit"),
                time=workout_dict.get("time"),
                comment=workout_dict.get("comment"),
                created_at=get_current_datetime(),
            )
            session.add(new_workout)
            session.commit()
            session.refresh(new_workout)
            return self._serialize(new_workout)

    def create_bulk(self, workouts: list[UpcomingWorkoutCreate]) -> list[dict]:
        """Create multiple upcoming workouts."""
        if not workouts:
            return []

        with SessionLocal() as session:
            categories_cache: dict[str, Category] = {}
            exercises_cache: dict[str, Exercise] = {}
            created = []

            for workout in workouts:
                workout_dict = workout.model_dump(exclude_none=False)
                category_name = workout_dict["category"]
                exercise_name = workout_dict["exercise"]

                category = categories_cache.get(category_name)
                if not category:
                    category = self._get_or_create_category(session, category_name)
                    categories_cache[category_name] = category

                exercise = exercises_cache.get(exercise_name)
                if not exercise:
                    exercise = self._get_or_create_exercise(
                        session, exercise_name, category
                    )
                    exercises_cache[exercise_name] = exercise

                new_workout = UpcomingWorkout(
                    session=workout_dict["session"],
                    is_mobility=workout_dict.get("is_mobility") or False,
                    exercise_id=exercise.id,
                    category_id=category.id,
                    weight=workout_dict.get("weight"),
                    reps=workout_dict.get("reps"),
                    distance=workout_dict.get("distance"),
                    distance_unit=workout_dict.get("distance_unit"),
                    time=workout_dict.get("time"),
                    comment=workout_dict.get("comment"),
                    created_at=get_current_datetime(),
                )
                session.add(new_workout)
                created.append(new_workout)

            session.commit()
            for workout in created:
                session.refresh(workout)

            return [self._serialize(workout) for workout in created]

    def delete_session(self, session_id: int) -> int:
        """Delete all workouts in a session. Returns count of deleted workouts."""
        with SessionLocal() as session:
            workouts = (
                session.execute(
                    select(UpcomingWorkout).where(
                        UpcomingWorkout.session == session_id,
                    )
                )
                .scalars()
                .all()
            )
            if not workouts:
                return 0

            for workout in workouts:
                session.delete(workout)

            session.commit()
            return len(workouts)

    def get_by_exercise(self, exercise: str) -> list[dict]:
        """Get all planned lifting sets for a specific exercise.

        Mobility sets are excluded because the caller is the progression
        service, which projects a 1RM curve forward from planned work. A
        prescribed stretch at bodyweight is not a data point on that curve.
        """
        with SessionLocal() as session:
            workouts = (
                session.execute(
                    select(UpcomingWorkout)
                    .join(Exercise)
                    .options(
                        selectinload(UpcomingWorkout.exercise),
                        selectinload(UpcomingWorkout.category),
                    )
                    .where(
                        Exercise.name == exercise,
                        UpcomingWorkout.is_mobility.is_(False),
                    )
                    .order_by(UpcomingWorkout.session.asc())
                )
                .scalars()
                .all()
            )
            return [self._serialize(workout) for workout in workouts]

    def delete_all(self) -> int:
        """Delete every upcoming workout. Returns the count.

        Unscoped on purpose: its caller is the Liftoscript generator, which
        clears the board — rows *and* their plans, deleted by the route —
        before writing a new program. The kind-scoped version existed to
        protect the pending mobility session from exactly this call; with one
        queue the protection is a warning on the generate button instead
        (9c4e7b21f806).
        """
        with SessionLocal() as session:
            workouts = session.execute(select(UpcomingWorkout)).scalars().all()

            count = len(workouts)
            for workout in workouts:
                session.delete(workout)

            session.commit()
            return count
