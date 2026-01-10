"""Upcoming workout data models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UpcomingWorkoutBase(BaseModel):
    """Base upcoming workout model."""

    session: int = Field(..., ge=1)
    exercise: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    weight: float | None = None
    weight_unit: str = "lbs"
    reps: int | None = None
    distance: float | None = None
    distance_unit: str | None = None
    time: str | None = None
    comment: str | None = None


class UpcomingWorkoutCreate(UpcomingWorkoutBase):
    """Model for creating an upcoming workout."""

    pass


class UpcomingWorkout(UpcomingWorkoutBase):
    """Full upcoming workout model with metadata."""

    id: int = Field(..., alias="doc_id")
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


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


class WendlerCurrentMaxes(BaseModel):
    """Current estimated 1RM values for main lifts."""

    squat: float | None = None
    bench: float | None = None
    deadlift: float | None = None


class LiftoscriptGenerateRequest(BaseModel):
    """Request to generate workouts from Liftoscript program."""

    script: str = Field(..., min_length=1, description="Liftoscript program text")
    num_cycles: int = Field(1, ge=1, le=52, description="Number of cycles to repeat the workouts")


class LiftoscriptGenerateResponse(BaseModel):
    """Response from generating Liftoscript workouts."""

    success: bool
    message: str
    count: int
    sessions: int
    deleted_count: int


class PresetInfo(BaseModel):
    """Information about an available preset."""

    name: str
    display_name: str
    description: str


class PresetContent(BaseModel):
    """Full preset content including script."""

    name: str
    display_name: str
    script: str
