"""Workout data models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class WorkoutBase(BaseModel):
    """Base workout model."""

    date: str = Field(..., description="Workout date in YYYY-MM-DD format")
    exercise: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    weight: Optional[float] = None
    weight_unit: str = "lbs"
    reps: Optional[int] = None
    distance: Optional[float] = None
    distance_unit: Optional[str] = None
    time: Optional[str] = None
    comment: Optional[str] = None
    completed_at: Optional[datetime] = None


class WorkoutCreate(WorkoutBase):
    """Model for creating a workout."""

    order: Optional[int] = None


class WorkoutUpdate(WorkoutBase):
    """Model for updating a workout."""

    order: Optional[int] = None


class Workout(WorkoutBase):
    """Full workout model with metadata."""

    id: int = Field(..., alias="doc_id")
    order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class WorkoutReorder(BaseModel):
    """Model for reordering workouts."""

    direction: str = Field(..., pattern="^(up|down)$")


class WorkoutBulkReorder(BaseModel):
    """Model for bulk reordering workouts by drag-and-drop."""

    workout_ids: list[int] = Field(..., description="Ordered list of workout IDs")


class WorkoutComplete(BaseModel):
    """Model for marking workout as complete."""

    completed: bool = Field(..., description="True to mark complete, False to mark incomplete")


class WorkoutMoveDate(BaseModel):
    """Model for moving all workouts to a different date."""

    target_date: str = Field(..., description="Target date in YYYY-MM-DD format")


class WorkoutMoveDateResponse(BaseModel):
    """Response for moving workouts to a different date."""

    source_date: str
    target_date: str
    count: int
    message: str


class WorkoutCopyDate(BaseModel):
    """Model for copying all workouts to a different date."""

    target_date: str = Field(..., description="Target date in YYYY-MM-DD format")


class WorkoutCopyDateResponse(BaseModel):
    """Response for copying workouts to a different date."""

    source_date: str
    target_date: str
    count: int
    message: str


class CalendarResponse(BaseModel):
    """Response for calendar workout counts."""

    year: int
    month: int
    counts: dict[str, int]
