"""Upcoming workout repository for database operations."""


from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.db.models import Category, Exercise, UpcomingWorkout
from app.models.upcoming import UpcomingWorkoutCreate
from app.utils.date_helpers import get_current_datetime
from app.utils.units import CANONICAL_WEIGHT_UNIT

#: A mobility program is one rolling routine, not a queue of them, so its rows
#: always share this session number. `session` is meaningful for lifting, where
#: a Liftoscript program generates many sessions at once and they are run in
#: order; for mobility there is only ever the next one, and an ordinal that
#: counts up would be a number with nothing to say.
MOBILITY_SESSION = 1

LIFTING = "lifting"
MOBILITY = "mobility"


class UpcomingWorkoutRepository:
    """Repository for upcoming workout data operations.

    Every method here is scoped to one `kind`. That is not defensive style — it
    is the whole cost of the single-table decision (Plan 0012 §2). `delete_all`
    unscoped would let generating a Liftoscript program silently destroy the
    pending mobility session, and `get_all` unscoped would put stretches in the
    lifting planner. The default is `'lifting'` everywhere, so an existing
    caller that has not been told about mobility keeps its old behaviour.
    """

    def _serialize(self, workout: UpcomingWorkout) -> dict:
        return {
            "doc_id": workout.id,
            "session": workout.session,
            "kind": workout.kind,
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

        Nothing about mobility is recorded here any more. A movement is not
        mobility work or lifting work; the *set* is (d7e4f2a91b83), and the
        planned row already knows which through `kind`. A good morning
        prescribed as a loaded stretch and the same good morning pulled heavy
        are one exercise row and two different sets.
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

    def get_all(self, kind: str = LIFTING) -> list[dict]:
        """Get all upcoming workouts of one kind, sorted by session."""
        with SessionLocal() as session:
            workouts = (
                session.execute(
                    select(UpcomingWorkout)
                    .options(
                        selectinload(UpcomingWorkout.exercise),
                        selectinload(UpcomingWorkout.category),
                    )
                    .where(UpcomingWorkout.kind == kind)
                    .order_by(UpcomingWorkout.session.asc(), UpcomingWorkout.id.asc())
                )
                .scalars()
                .all()
            )
            return [self._serialize(workout) for workout in workouts]

    def get_by_session(self, session_id: int, kind: str = LIFTING) -> list[dict]:
        """Get all workouts for a specific session.

        Ordered by `id`, which is insertion order. The table has no `order`
        column, so for mobility this is the prescribed order of the routine —
        the agent writes the items in the sequence they are to be performed and
        that sequence is carried by nothing else.
        """
        with SessionLocal() as session:
            workouts = (
                session.execute(
                    select(UpcomingWorkout)
                    .options(
                        selectinload(UpcomingWorkout.exercise),
                        selectinload(UpcomingWorkout.category),
                    )
                    .where(
                        UpcomingWorkout.session == session_id,
                        UpcomingWorkout.kind == kind,
                    )
                    .order_by(UpcomingWorkout.id.asc())
                )
                .scalars()
                .all()
            )
            return [self._serialize(workout) for workout in workouts]

    def get_lowest_session(self, kind: str = LIFTING) -> int | None:
        """Get the lowest session number."""
        with SessionLocal() as session:
            lowest = session.execute(
                select(UpcomingWorkout.session)
                .where(UpcomingWorkout.kind == kind)
                .order_by(UpcomingWorkout.session.asc())
                .limit(1)
            ).scalar_one_or_none()
            return lowest

    def create(self, workout: UpcomingWorkoutCreate) -> dict:
        """Create a new upcoming workout."""
        workout_dict = workout.model_dump(exclude_none=False)

        kind = workout_dict.get("kind") or LIFTING

        with SessionLocal() as session:
            category = self._get_or_create_category(session, workout_dict["category"])
            exercise = self._get_or_create_exercise(
                session, workout_dict["exercise"], category
            )

            new_workout = UpcomingWorkout(
                session=workout_dict["session"],
                kind=kind,
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
                kind = workout_dict.get("kind") or LIFTING

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
                    kind=kind,
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

    def delete_session(self, session_id: int, kind: str = LIFTING) -> int:
        """Delete all workouts in a session. Returns count of deleted workouts."""
        with SessionLocal() as session:
            workouts = (
                session.execute(
                    select(UpcomingWorkout).where(
                        UpcomingWorkout.session == session_id,
                        UpcomingWorkout.kind == kind,
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

    def get_by_exercise(self, exercise: str, kind: str = LIFTING) -> list[dict]:
        """Get all upcoming workouts for a specific exercise.

        Lifting-only by default because the caller is the progression service,
        which projects a 1RM curve forward from planned work. A prescribed
        stretch at bodyweight is not a data point on that curve.
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
                    .where(Exercise.name == exercise, UpcomingWorkout.kind == kind)
                    .order_by(UpcomingWorkout.session.asc())
                )
                .scalars()
                .all()
            )
            return [self._serialize(workout) for workout in workouts]

    def delete_all(self, kind: str = LIFTING) -> int:
        """Delete every upcoming workout of one kind. Returns the count.

        The `kind` scope is the reason this is not `DELETE FROM
        upcoming_workouts`. Its caller is the Liftoscript generator, which
        clears the board before writing a new program — unscoped, generating a
        lifting program would take the pending mobility session with it, and
        the mobility page would go back to "needs generation" for a reason the
        user could not see.
        """
        with SessionLocal() as session:
            workouts = (
                session.execute(
                    select(UpcomingWorkout).where(UpcomingWorkout.kind == kind)
                )
                .scalars()
                .all()
            )

            count = len(workouts)
            for workout in workouts:
                session.delete(workout)

            session.commit()
            return count
