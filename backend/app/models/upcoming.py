"""Upcoming workout data models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class UpcomingWorkoutBase(BaseModel):
    """Base upcoming workout model."""
    session: int = Field(..., ge=1)
    exercise: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    weight: Optional[float] = None
    weight_unit: str = "lbs"
    reps: Optional[int | str] = None
    distance: Optional[float] = None
    distance_unit: Optional[str] = None
    time: Optional[str] = None
    comment: Optional[str] = None


class UpcomingWorkoutCreate(UpcomingWorkoutBase):
    """Model for creating an upcoming workout."""
    pass


class UpcomingWorkout(UpcomingWorkoutBase):
    """Full upcoming workout model with metadata."""
    id: int = Field(..., alias="doc_id")
    created_at: datetime

    class Config:
        populate_by_name = True
        from_attributes = True


class UpcomingWorkoutBulkCreate(BaseModel):
    """Model for bulk creating upcoming workouts."""
    workouts: list[UpcomingWorkoutCreate]


class SessionTransferRequest(BaseModel):
    """Request to transfer a session to historical workouts."""
    date: str = Field(..., description="Target date in YYYY-MM-DD format")


class SessionTransferResponse(BaseModel):
    """Response from transferring a session."""
    session: int
    date: str
    count: int
    message: str
