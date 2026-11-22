"""Upcoming workout data models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UpcomingWorkoutBase(BaseModel):
    """Base upcoming workout model."""

    session: int = Field(..., ge=1)
    #: Whether this prescribed set is mobility work. The same fact
    #: `workouts.is_mobility` records once it is logged; transfer carries it.
    is_mobility: bool = False
    exercise: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    weight: float | None = None
    weight_unit: str = "lbs"
    reps: int | None = None
    distance: float | None = None
    distance_unit: str | None = None
    time: str | None = None
    comment: str | None = None
    # Target timing, carried onto the day's set at transfer (842c1976c18a).
    work_seconds: int | None = Field(None, ge=1, le=3600)
    rest_seconds: int | None = Field(None, ge=0, le=3600)
    rest_after_seconds: int | None = Field(None, ge=0, le=3600)


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


class UpcomingSession(BaseModel):
    """One session of the upcoming queue, with its plan metadata if it has any.

    The queue is one list (9c4e7b21f806). Sessions written by the agent carry
    the `label`, `rationale` and `generated_at` that `mobility_plan` holds for
    them; a Liftoscript-generated session has none, because a script has
    nothing to say about why — the program editor is right there.
    """

    session: int
    label: str | None = None
    rationale: str | None = None
    generated_at: str | None = None
    items: list[UpcomingWorkout] = Field(default_factory=list)


class SessionTransferRequest(BaseModel):
    """Request to transfer a session to historical workouts."""

    date: str = Field(..., description="Target date in YYYY-MM-DD format")


class SessionTransferResponse(BaseModel):
    """Response from transferring a session."""

    session: int
    date: str
    count: int
    #: The agent-written session's label, when the session had a plan. None
    #: for a Liftoscript-generated session, which has nothing to promote.
    label: str | None = None
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


class LiftoscriptProgram(BaseModel):
    """The program a generate last ran, so the editor can reopen with it."""

    script: str
    num_cycles: int
    generated_at: str


class PresetContent(BaseModel):
    """Full preset content including script."""

    name: str
    display_name: str
    script: str
