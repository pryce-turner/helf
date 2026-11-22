"""Workout preset data models — hand-built workouts applied to a day (plan 0020)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PresetItemBase(BaseModel):
    """One tile of a preset: the *targets* a planned workout tile carries.

    Field for field the target half of `WorkoutBase`, so the day editor can
    send the same form for either. There is no date and no completion: a
    preset is never performed, the day it is applied to is.
    """

    exercise: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    weight: float | None = None
    weight_unit: str = "lbs"
    reps: int | None = None
    distance: float | None = None
    distance_unit: str | None = None
    comment: str | None = None
    is_mobility: bool = False
    work_seconds: int | None = Field(None, ge=1, le=3600)
    rest_seconds: int | None = Field(None, ge=0, le=3600)
    rest_after_seconds: int | None = Field(None, ge=0, le=3600)


class PresetItemCreate(PresetItemBase):
    """Omitted, `order` appends after the preset's last tile."""

    order: int | None = None


class PresetItemUpdate(PresetItemBase):
    """A full replace of the tile's targets, like a workout PUT."""

    order: int | None = None


class PresetItem(PresetItemBase):
    id: int = Field(..., alias="doc_id")
    preset_id: int
    order: int

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("A preset needs a name")
    return value


class PresetCreate(BaseModel):
    """Omitted, the name is "New preset" (numbered if that one is taken), so
    the Add button can create one before the user has typed anything."""

    name: str | None = None

    _clean = field_validator("name")(_clean_name)


class PresetUpdate(BaseModel):
    name: str

    _clean = field_validator("name")(_clean_name)


class Preset(BaseModel):
    id: int = Field(..., alias="doc_id")
    name: str
    created_at: datetime
    updated_at: datetime
    items: list[PresetItem]

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class PresetReorder(BaseModel):
    item_ids: list[int] = Field(..., description="The preset's item IDs, in their new order")


class PresetApply(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")


class PresetApplyResponse(BaseModel):
    preset_id: int
    date: str
    count: int
    message: str
