"""Workout repository for database operations."""


from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.db.models import Category, Exercise, Workout
from app.repositories.exercise_repo import ExerciseRepository
from app.models.workout import WorkoutCreate, WorkoutUpdate
from app.utils.date_helpers import get_current_datetime
from app.utils.durations import parse_duration_seconds
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
            # Targets, then actuals (plan 0018). A planned tile has the first
            # and none of the second.
            "work_seconds": workout.work_seconds,
            "rest_seconds": workout.rest_seconds,
            "rest_after_seconds": workout.rest_after_seconds,
            "completed_reps": workout.completed_reps,
            "actual_work_seconds": workout.actual_work_seconds,
            "actual_rest_seconds": workout.actual_rest_seconds,
            "actual_rest_after_seconds": workout.actual_rest_after_seconds,
            "ended_early": bool(workout.ended_early),
        }

    @staticmethod
    def _derive_actuals(workout: Workout) -> None:
        """Fill a naturally completed tile's actuals from its targets.

        Shared by the manual tick and by a row created already completed:
        ordinary completion without a timer means "the target is what
        happened". The actuals are **totals** — two 40s reps are 80s of work,
        and the per-rep rest runs only between reps, never after the last.
        The rest-after divider is deliberately not derived — it is recorded
        separately, by the player, when it actually runs.
        """
        reps = workout.reps or 1
        workout.completed_reps = workout.reps
        workout.actual_work_seconds = (
            workout.work_seconds * reps if workout.work_seconds is not None else None
        )
        workout.actual_rest_seconds = (
            workout.rest_seconds * (reps - 1)
            if workout.rest_seconds is not None
            else None
        )
        workout.ended_early = False

    @staticmethod
    def _clear_actuals(workout: Workout) -> None:
        """Return a tile to purely planned: no performance without a completion."""
        workout.completed_reps = None
        workout.actual_work_seconds = None
        workout.actual_rest_seconds = None
        workout.actual_rest_after_seconds = None
        workout.ended_early = False

    @staticmethod
    def _apply_field_config(workout_dict: dict, exercise: Exercise) -> None:
        """Null the fields of any group the exercise has disabled.

        Ordinary manual creation can fill only enabled fields (plan 0018):
        the day view does not offer them, and this is the second line, so a
        caller working from a stale configuration loses the value rather
        than writing a tile the movement says it does not take. Existing
        tiles are never rewritten — this runs on create only.
        """
        if not exercise.reps_enabled:
            workout_dict["reps"] = None
        if not exercise.weight_enabled:
            workout_dict["weight"] = None
        if not exercise.distance_enabled:
            workout_dict["distance"] = None
            workout_dict["distance_unit"] = None
        if not exercise.time_enabled:
            workout_dict["work_seconds"] = None
            workout_dict["rest_seconds"] = None
            workout_dict["rest_after_seconds"] = None

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

            # Ordinary manual creation can fill only enabled fields (plan
            # 0018). Groups the exercise has disabled come back NULL whoever
            # sent them.
            self._apply_field_config(workout_dict, exercise)

            # With no position given, the next set goes below the bottom-most
            # completed one, not after everything: while a session is under way
            # the sets under that line are the ones not yet run, and a set
            # appended behind them is out of sequence. Nothing completed →
            # append, as before.
            if workout_dict.get("order") is None:
                workout_dict["order"] = self._open_slot_after_last_completed(session, workout.date)

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
                # `time` is read-only legacy (plan 0018): accepted on the way
                # in for compatibility, never written. New tiles carry the
                # numeric targets below.
                time=None,
                comment=workout_dict.get("comment"),
                order=order_value,
                created_at=now,
                updated_at=now,
                completed_at=workout_dict.get("completed_at"),
                is_mobility=bool(workout_dict.get("is_mobility")),
                work_seconds=workout_dict.get("work_seconds"),
                rest_seconds=workout_dict.get("rest_seconds"),
                rest_after_seconds=workout_dict.get("rest_after_seconds"),
            )
            # A row created already completed was performed at creation, so it
            # derives its actuals the same way a manual tick does.
            if new_workout.completed_at is not None:
                self._derive_actuals(new_workout)
            session.add(new_workout)
            session.commit()
            session.refresh(new_workout)
            session.refresh(exercise)
            session.refresh(category)
            # Serialised inside the session: `_serialize` walks the
            # relationships, which a closed session cannot load.
            result = self._serialize(new_workout)

        # Usage moves at *performance* time, not suggestion time (plan 0018):
        # an unplayed tile must not affect the next shuffle or the recent
        # list, so only a row born completed counts here — the performance
        # paths (`toggle_complete`, `perform`) maintain the rest.
        if result["completed_at"] is not None:
            ExerciseRepository().update_usage(workout_dict["exercise"], workout.date)
        return result

    @staticmethod
    def _open_slot_after_last_completed(session, date: str) -> int | None:
        """Free the position below the day's bottom-most completed set.

        Returns the `order` for the new set, or None when nothing on the day is
        completed. Only the sets below the anchor that would otherwise collide
        are moved, and each by the least it takes: every UPDATE here fires an
        audit trigger, and `audit_log` cannot be tidied afterwards. Sorting on
        (order, id) keeps this well-defined on days whose orders have gaps or
        duplicates.
        """
        day = session.execute(
            select(Workout).where(Workout.date == date).order_by(Workout.order.asc(), Workout.id.asc())
        ).scalars().all()
        anchor = max(
            (i for i, w in enumerate(day) if w.completed_at is not None),
            default=None,
        )
        if anchor is None:
            return None

        slot = (day[anchor].order or 0) + 1
        next_free = slot + 1
        for w in day[anchor + 1:]:
            if (w.order or 0) < next_free:
                w.order = next_free
            next_free = w.order + 1
        return slot

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
            # `time` is never written (read-only legacy, plan 0018) — a
            # legacy value on the row survives every edit, and no new one is
            # ever stored.
            existing.comment = workout_dict.get("comment")
            if workout_dict.get("order") is not None:
                existing.order = workout_dict.get("order")
            # Sticky unless explicitly sent — same `model_fields_set`
            # distinction as `is_mobility` below. An edit form is not a
            # performance write: a PUT carrying only a comment must not
            # uncomplete a performed tile, and the day view's editor does not
            # send `completed_at` at all.
            if "completed_at" in workout.model_fields_set:
                existing.completed_at = workout_dict.get("completed_at")
            # The target timing is edit-form business, sticky the same way:
            # a client that does not know these fields must not wipe them by
            # omitting them, and an explicit null is how one clears. The
            # *actuals* are not writable here at all — they belong to the
            # performance paths alone, so no edit can rewrite what happened.
            for field in ("work_seconds", "rest_seconds", "rest_after_seconds"):
                if field in workout.model_fields_set:
                    setattr(existing, field, workout_dict.get(field))
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
        """Mark a workout as complete or incomplete.

        Manual completion is a performance write without a timer: completing
        derives the actuals from the targets ("the target is what happened"),
        and uncompleting clears them, so a tile only ever carries performance
        while it is performed. Usage moves with it — a suggestion never does.

        Both directions are idempotent: ticking an already-ticked tile is a
        no-op rather than an overwrite of the player's measured actuals (or a
        second use count), and unticking a planned tile writes nothing.
        """
        with SessionLocal() as session:
            workout = session.get(Workout, doc_id)
            if not workout:
                return None

            if completed and workout.completed_at is not None:
                return self._serialize(workout)
            if not completed and workout.completed_at is None:
                return self._serialize(workout)

            now = get_current_datetime()
            if completed:
                workout.completed_at = now
                self._derive_actuals(workout)
            else:
                workout.completed_at = None
                self._clear_actuals(workout)
            workout.updated_at = now
            exercise_name = workout.exercise.name
            session.commit()
            session.refresh(workout)
            result = self._serialize(workout)

        if completed:
            ExerciseRepository().update_usage(exercise_name, result["date"])
        return result

    def perform(
        self,
        doc_id: int,
        *,
        ended_early: bool,
        completed_reps: int | None = None,
        actual_work_seconds: float | None = None,
        actual_rest_seconds: float | None = None,
    ) -> dict | None:
        """Write one tile's performance, as measured by the day player.

        Natural completion (`ended_early=False`) derives the full actuals
        from the targets; a Stop takes the measured values. The server
        assigns `completed_at` **and the date**: work is logged on the day it
        is performed (plan 0018), so a tile played on another day moves to
        today, at the end of it. The rest-after divider is not part of this
        write — it is recorded separately, by `record_rest_after`, when it
        actually runs.
        """
        with SessionLocal() as session:
            workout = session.get(Workout, doc_id)
            if not workout:
                return None

            # A tile already performed answers as it is: a lost response
            # makes the player's Retry repeat the write, and the repeat must
            # not move the completion, the date or the order, nor count the
            # movement a second time.
            if workout.completed_at is not None:
                return self._serialize(workout)

            now = get_current_datetime()
            today = now.date().isoformat()
            workout.completed_at = now
            if workout.date != today:
                # Move to the day the work actually happened on, after
                # anything already there.
                highest = session.execute(
                    select(func.max(Workout.order)).where(Workout.date == today)
                ).scalar()
                workout.date = today
                workout.order = (highest or 0) + 1
            workout.ended_early = ended_early
            if ended_early:
                workout.completed_reps = completed_reps
                workout.actual_work_seconds = actual_work_seconds
                workout.actual_rest_seconds = actual_rest_seconds
            else:
                # Natural completion: derived from the targets, but an
                # explicitly sent value wins — the player writes from its
                # immutable snapshot, and a tile edited mid-run must not
                # change what the run records (plan 0018).
                self._derive_actuals(workout)
                if completed_reps is not None:
                    workout.completed_reps = completed_reps
                if actual_work_seconds is not None:
                    workout.actual_work_seconds = actual_work_seconds
                if actual_rest_seconds is not None:
                    workout.actual_rest_seconds = actual_rest_seconds
            workout.updated_at = now
            exercise_name = workout.exercise.name
            session.commit()
            session.refresh(workout)
            result = self._serialize(workout)

        ExerciseRepository().update_usage(exercise_name, today)
        return result

    def record_rest_after(self, doc_id: int, seconds: float) -> dict | None:
        """Record the rest divider that ran after a tile, on *that* tile.

        Whole on a full run, partial on a Stop. The next tile is not
        involved — a Stop during the divider leaves it planned, which is the
        whole reason this write exists apart from `perform`.
        """
        with SessionLocal() as session:
            workout = session.get(Workout, doc_id)
            if not workout:
                return None
            if workout.completed_at is None:
                raise ValueError(
                    "cannot record a rest-after on a tile that was not performed"
                )

            workout.actual_rest_after_seconds = seconds
            workout.updated_at = get_current_datetime()
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

    def set_mobility_for_date(self, date: str, is_mobility: bool) -> tuple[int, int]:
        """Flag every set on `date` as mobility work, or clear every one.

        Returns `(changed, total)`. **Only rows whose flag actually differs are
        written.** Every UPDATE on `workouts` fires an audit trigger, so
        touching rows that already hold the value would fill `audit_log` with
        entries whose old and new values are identical — noise in the one table
        that cannot be cleaned up afterwards.

        This is a bulk edit of per-set flags, not a day-level marker. The
        distinction is the whole of plan 0013 §6: nothing is stored about the
        day, and a day whose sets disagree is a perfectly good state that this
        endpoint simply does not happen to produce.
        """
        with SessionLocal() as session:
            workouts = session.execute(
                select(Workout).where(Workout.date == date)
            ).scalars().all()
            if not workouts:
                return 0, 0

            now = get_current_datetime()
            changed = 0
            for workout in workouts:
                if bool(workout.is_mobility) == is_mobility:
                    continue
                workout.is_mobility = is_mobility
                workout.updated_at = now
                changed += 1

            session.commit()
            return changed, len(workouts)

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
                    # No legacy `time` forward: read-only legacy stays on the
                    # row it was written on; copies are new tiles.
                    time=None,
                    comment=source_workout.comment,
                    order=starting_order + i,
                    created_at=now,
                    updated_at=now,
                    # A copy of a performed tile is a *planned* tile: targets
                    # survive, completion and every actual reset (plan 0018).
                    # A legacy-timed row with no numeric target yet keeps its
                    # duration through the parser rather than losing it.
                    completed_at=None,
                    work_seconds=(
                        source_workout.work_seconds
                        if source_workout.work_seconds is not None
                        else parse_duration_seconds(source_workout.time)
                    ),
                    rest_seconds=source_workout.rest_seconds,
                    rest_after_seconds=source_workout.rest_after_seconds,
                    # Copied sets keep their intent: a mobility session
                    # copied to another date is still mobility work.
                    is_mobility=source_workout.is_mobility,
                )
                session.add(new_workout)

            session.commit()
            return len(source_workouts)

    def get_workout_counts_by_date(self, year: int, month: int) -> dict[str, int]:
        """Get workout counts grouped by date for a specific month.

        **Performed tiles only.** A day of unplayed suggestions is a planned
        day, not training, and the calendar dot must not claim otherwise
        (plan 0018).
        """
        pattern = f"{year}-{month:02d}-%"

        with SessionLocal() as session:
            rows = session.execute(
                select(Workout.date, func.count())
                .where(Workout.date.like(pattern))
                .where(Workout.completed_at.is_not(None))
                .group_by(Workout.date)
            ).all()

            return {date: count for date, count in rows}

    def get_by_exercise(self, exercise: str) -> list[dict]:
        """Get all workouts for a specific exercise.

        Performed tiles only: a planned tile has targets, and a target is not
        a performance — an unplayed 100 lb suggestion must not move a 1RM
        estimate or appear in the history it is derived from.
        """
        with SessionLocal() as session:
            workouts = session.execute(
                select(Workout)
                .join(Exercise)
                .options(selectinload(Workout.exercise), selectinload(Workout.category))
                .where(Exercise.name == exercise)
                .where(Workout.completed_at.is_not(None))
                # `order` as the tiebreak so a day's sets come back in the
                # sequence they were performed, which is what the progression
                # history lists under each date.
                .order_by(Workout.date.asc(), Workout.order.asc())
            ).scalars().all()
            return [self._serialize(workout) for workout in workouts]
