"""Workout data models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class WorkoutBase(BaseModel):
    """Base workout model."""
    date: str = Field(..., description="Workout date in YYYY-MM-DD format")
    exercise: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    weight: Optional[float] = None
    weight_unit: str = "lbs"
    reps: Optional[int | str] = None  # Can be int or string like "5+"
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

    class Config:
        populate_by_name = True
        from_attributes = True


class WorkoutReorder(BaseModel):
    """Model for reordering workouts."""
    direction: str = Field(..., pattern="^(up|down)$")


class WorkoutComplete(BaseModel):
    """Model for marking workout as complete."""
    completed: bool = Field(..., description="True to mark complete, False to mark incomplete")


class CalendarResponse(BaseModel):
    """Response for calendar workout counts."""
    year: int
    month: int
    counts: dict[str, int]
