"""Workout preset repository — hand-built workouts applied to a day (plan 0020).

`database.SessionLocal` is reached through the module deliberately; see the
header of `food_repo.py`.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app import database
from app.db.models import Workout, WorkoutPreset, WorkoutPresetItem
from app.models.preset import PresetItemCreate, PresetItemUpdate
from app.repositories.workout_repo import WorkoutRepository
from app.utils.date_helpers import get_current_datetime
from app.utils.units import CANONICAL_WEIGHT_UNIT

DEFAULT_NAME = "New preset"


class PresetNameTakenError(ValueError):
    """The name is how the list tells presets apart, so it must be unique."""


class PresetRepository:
    """Presets and their tiles, and applying one to a date."""

    def __init__(self) -> None:
        # Category and exercise resolution, and the field-config guard, are
        # the day's rules — a preset tile is a planned tile, so it shares them.
        self._workouts = WorkoutRepository()

    @staticmethod
    def _serialize_item(item: WorkoutPresetItem) -> dict:
        return {
            "doc_id": item.id,
            "preset_id": item.preset_id,
            "order": item.order,
            "exercise": item.exercise.name,
            "category": item.category.name,
            "weight": item.weight,
            "weight_unit": CANONICAL_WEIGHT_UNIT,
            "reps": item.reps,
            "distance": item.distance,
            "distance_unit": item.distance_unit,
            "comment": item.comment,
            "is_mobility": bool(item.is_mobility),
            "work_seconds": item.work_seconds,
            "rest_seconds": item.rest_seconds,
            "rest_after_seconds": item.rest_after_seconds,
        }

    def _serialize(self, preset: WorkoutPreset) -> dict:
        return {
            "doc_id": preset.id,
            "name": preset.name,
            "created_at": preset.created_at,
            "updated_at": preset.updated_at,
            "items": [self._serialize_item(i) for i in preset.items],
        }

    @staticmethod
    def _load(session, preset_id: int) -> WorkoutPreset | None:
        return session.execute(
            select(WorkoutPreset)
            .where(WorkoutPreset.id == preset_id)
            .options(
                selectinload(WorkoutPreset.items).selectinload(WorkoutPresetItem.exercise),
                selectinload(WorkoutPreset.items).selectinload(WorkoutPresetItem.category),
            )
        ).scalar_one_or_none()

    @staticmethod
    def _touch(session, preset_id: int) -> None:
        preset = session.get(WorkoutPreset, preset_id)
        if preset is not None:
            preset.updated_at = get_current_datetime()

    @staticmethod
    def _unused_default_name(session) -> str:
        taken = set(
            session.execute(
                select(WorkoutPreset.name).where(WorkoutPreset.name.like(f"{DEFAULT_NAME}%"))
            ).scalars()
        )
        if DEFAULT_NAME not in taken:
            return DEFAULT_NAME
        n = 2
        while f"{DEFAULT_NAME} {n}" in taken:
            n += 1
        return f"{DEFAULT_NAME} {n}"

    # --- presets --------------------------------------------------------

    def get_all(self) -> list[dict]:
        with database.SessionLocal() as session:
            presets = session.execute(
                select(WorkoutPreset)
                .order_by(WorkoutPreset.name)
                .options(
                    selectinload(WorkoutPreset.items).selectinload(WorkoutPresetItem.exercise),
                    selectinload(WorkoutPreset.items).selectinload(WorkoutPresetItem.category),
                )
            ).scalars().all()
            return [self._serialize(p) for p in presets]

    def get_by_id(self, preset_id: int) -> dict | None:
        with database.SessionLocal() as session:
            preset = self._load(session, preset_id)
            return self._serialize(preset) if preset else None

    def create(self, name: str | None = None) -> dict:
        now = get_current_datetime()
        with database.SessionLocal() as session:
            preset = WorkoutPreset(
                name=name or self._unused_default_name(session),
                created_at=now,
                updated_at=now,
            )
            session.add(preset)
            try:
                session.commit()
            except IntegrityError as exc:
                raise PresetNameTakenError(f"A preset named '{preset.name}' already exists") from exc
            return self._serialize(self._load(session, preset.id))

    def rename(self, preset_id: int, name: str) -> dict | None:
        with database.SessionLocal() as session:
            preset = session.get(WorkoutPreset, preset_id)
            if preset is None:
                return None
            preset.name = name
            preset.updated_at = get_current_datetime()
            try:
                session.commit()
            except IntegrityError as exc:
                raise PresetNameTakenError(f"A preset named '{name}' already exists") from exc
            return self._serialize(self._load(session, preset_id))

    def delete(self, preset_id: int) -> bool:
        """Its tiles go by cascade. Days it was applied to keep their rows:
        they were copies, and nothing points back here."""
        with database.SessionLocal() as session:
            preset = session.get(WorkoutPreset, preset_id)
            if preset is None:
                return False
            session.delete(preset)
            session.commit()
            return True

    # --- tiles ----------------------------------------------------------

    def _fill_item(
        self, session, item: WorkoutPresetItem, data: PresetItemCreate | PresetItemUpdate
    ) -> None:
        values = data.model_dump(exclude_none=False)
        category = self._workouts._get_or_create_category(session, values["category"])
        exercise = self._workouts._get_or_create_exercise(session, values["exercise"], category)
        # Same guard as a workout create (plan 0018): a group the exercise has
        # disabled cannot be filled, whatever a stale client sends.
        WorkoutRepository._apply_field_config(values, exercise)
        item.exercise_id = exercise.id
        item.category_id = category.id
        for field in (
            "weight",
            "reps",
            "distance",
            "distance_unit",
            "comment",
            "work_seconds",
            "rest_seconds",
            "rest_after_seconds",
        ):
            setattr(item, field, values.get(field))
        item.is_mobility = bool(values.get("is_mobility"))

    def add_item(self, preset_id: int, data: PresetItemCreate) -> dict | None:
        with database.SessionLocal() as session:
            if session.get(WorkoutPreset, preset_id) is None:
                return None
            order = data.order
            if order is None:
                last = session.execute(
                    select(func.max(WorkoutPresetItem.order)).where(
                        WorkoutPresetItem.preset_id == preset_id
                    )
                ).scalar_one()
                order = (last or 0) + 1
            item = WorkoutPresetItem(preset_id=preset_id, order=order)
            self._fill_item(session, item, data)
            session.add(item)
            self._touch(session, preset_id)
            session.commit()
            session.refresh(item)
            return self._serialize_item(item)

    def update_item(self, item_id: int, data: PresetItemUpdate) -> dict | None:
        with database.SessionLocal() as session:
            item = session.get(WorkoutPresetItem, item_id)
            if item is None:
                return None
            self._fill_item(session, item, data)
            if data.order is not None:
                item.order = data.order
            self._touch(session, item.preset_id)
            session.commit()
            session.refresh(item)
            return self._serialize_item(item)

    def delete_item(self, item_id: int) -> bool:
        with database.SessionLocal() as session:
            item = session.get(WorkoutPresetItem, item_id)
            if item is None:
                return False
            self._touch(session, item.preset_id)
            session.delete(item)
            session.commit()
            return True

    def reorder(self, preset_id: int, item_ids: list[int]) -> bool | None:
        """`None` for a missing preset; ids that are not its tiles are ignored,
        so a stale list cannot move another preset's rows."""
        with database.SessionLocal() as session:
            if session.get(WorkoutPreset, preset_id) is None:
                return None
            items = {
                i.id: i
                for i in session.execute(
                    select(WorkoutPresetItem).where(WorkoutPresetItem.preset_id == preset_id)
                ).scalars()
            }
            for order, item_id in enumerate(item_ids, start=1):
                if item_id in items:
                    items[item_id].order = order
            self._touch(session, preset_id)
            session.commit()
            return True

    # --- applying -------------------------------------------------------

    def apply(self, preset_id: int, date: str) -> int | None:
        """Copy every tile onto `date` as planned workout rows.

        They append after whatever the day already holds — applying never
        displaces work — and arrive **planned**: no completion, no actuals,
        and `exercises.last_used` untouched, since usage moves at performance
        (plan 0018). Each tile's mobility flag travels with it.
        """
        with database.SessionLocal() as session:
            preset = self._load(session, preset_id)
            if preset is None:
                return None
            if not preset.items:
                return 0
            last = session.execute(
                select(func.max(Workout.order)).where(Workout.date == date)
            ).scalar_one()
            start = (last or 0) + 1
            now = get_current_datetime()
            for offset, item in enumerate(preset.items):
                session.add(
                    Workout(
                        date=date,
                        exercise_id=item.exercise_id,
                        category_id=item.category_id,
                        weight=item.weight,
                        reps=item.reps,
                        distance=item.distance,
                        distance_unit=item.distance_unit,
                        time=None,
                        comment=item.comment,
                        order=start + offset,
                        created_at=now,
                        updated_at=now,
                        completed_at=None,
                        is_mobility=bool(item.is_mobility),
                        work_seconds=item.work_seconds,
                        rest_seconds=item.rest_seconds,
                        rest_after_seconds=item.rest_after_seconds,
                    )
                )
            session.commit()
            return len(preset.items)
