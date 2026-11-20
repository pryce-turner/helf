"""Workout data models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkoutBase(BaseModel):
    """Base workout model — one set tile, with its *target* values.

    Targets are what the tile asks for; what was actually performed lives on
    the response only (`Workout`), written by the performance endpoints and
    the completion toggle, never by a create or an edit (plan 0018).
    """

    date: str = Field(..., description="Workout date in YYYY-MM-DD format")
    exercise: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    weight: float | None = None
    weight_unit: str = "lbs"
    reps: int | None = None
    distance: float | None = None
    distance_unit: str | None = None
    # Legacy free-form duration, read-only in practice: new tiles write the
    # numeric fields below.
    time: str | None = None
    comment: str | None = None
    completed_at: datetime | None = None
    # Whether *this set* was mobility work. A property of the performance, not
    # of the movement: the same exercise is a lift one day and a loaded stretch
    # the next. A mobility day is derived from these (d7e4f2a91b83), which is
    # what the agent reads to write the next session.
    is_mobility: bool = False
    # Target timing, fillable only for exercises with Time enabled — the
    # repository nulls the rest on create, so a stale client cannot write a
    # tile the movement says it does not take.
    work_seconds: int | None = Field(None, ge=1, le=3600)
    rest_seconds: int | None = Field(None, ge=0, le=3600)
    rest_after_seconds: int | None = Field(None, ge=0, le=3600)


class WorkoutCreate(WorkoutBase):
    """Model for creating a workout."""

    # Omitted, the set goes directly below the day's bottom-most completed set
    # (see WorkoutRepository.create). Callers that place rows themselves - the
    # transfer paths - pass it explicitly.
    order: int | None = None


class WorkoutUpdate(WorkoutBase):
    """Model for updating a workout."""

    order: int | None = None


class WorkoutPerform(BaseModel):
    """One tile's performance, as measured by the day player.

    Natural completion sends nothing — the server derives the full actuals
    from the targets. A Stop sends what was measured up to that instant and
    `ended_early: true`; the targets stay, so the shortfall is readable.
    `completed_at` and the date are the server's: work is logged on the day
    it is performed.
    """

    ended_early: bool = False
    completed_reps: int | None = Field(None, ge=0)
    actual_work_seconds: float | None = Field(None, ge=0)
    actual_rest_seconds: float | None = Field(None, ge=0)


class WorkoutRestAfter(BaseModel):
    """The rest divider after a tile, measured — partial on Stop, whole on a
    full run. Written to the *preceding* tile, never to a row of its own."""

    actual_rest_after_seconds: float = Field(..., ge=0)


class Workout(WorkoutBase):
    """Full workout model with metadata — targets *and* actuals."""

    id: int = Field(..., alias="doc_id")
    order: int
    created_at: datetime
    updated_at: datetime
    # Actual performance. NULL until the tile is performed; written only by
    # the performance paths, so an edit cannot rewrite what happened.
    completed_reps: int | None = None
    actual_work_seconds: float | None = None
    actual_rest_seconds: float | None = None
    actual_rest_after_seconds: float | None = None
    ended_early: bool = False

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


class WorkoutDayMobility(BaseModel):
    """Set or clear the mobility flag on every set of a day."""

    is_mobility: bool


class WorkoutDayMobilityResponse(BaseModel):
    """`changed` counts rows actually written, which is not `total`.

    Sending the state a day is already in is a no-op that reports `changed: 0`
    rather than an error — the caller is a button that knows the state it
    wants, and pressing it twice should mean what pressing it once meant.
    """

    date: str
    is_mobility: bool
    changed: int
    total: int
    message: str


class CalendarResponse(BaseModel):
    """Response for calendar workout counts."""

    year: int
    month: int
    counts: dict[str, int]
