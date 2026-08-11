"""Mobility session schemas — the HTTP contract for the mobility tab.

Separate from `models/upcoming.py` because the shapes differ even though the
storage does not. A lifting plan is a list of sessions the user generated from
a script; a mobility plan is *one* session the agent wrote, and the page around
it needs the reasoning as much as the movements.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.models.upcoming import UpcomingWorkout


class MobilityLoggedSet(BaseModel):
    """One set as it was actually logged, with whatever was said about it."""

    exercise: str
    weight: float | None = None
    reps: int | None = None
    time: str | None = None
    comment: str | None = None
    order: int
    completed: bool = False


class MobilityLastSession(BaseModel):
    """The last mobility session that reached the calendar."""

    date: str
    rationale: str
    sets: list[MobilityLoggedSet]


class MobilityPending(BaseModel):
    """What the mobility tab renders, in either of its two states.

    `ready` is the state discriminator and is derived, not stored: a session is
    ready precisely when it has items. There is no third state and no
    'generating' - the agent writes the session in one transaction over MCP, so
    from the page's point of view a session either exists or does not.

    `last_session` is present in both states on purpose. When nothing is
    pending it is what makes the empty state actionable, because it carries the
    comments the next session has to be written from.
    """

    ready: bool
    items: list[UpcomingWorkout] = Field(default_factory=list)
    rationale: str | None = None
    generated_at: str | None = None
    last_session: MobilityLastSession | None = None

    model_config = ConfigDict(populate_by_name=True)


class MobilityTransferRequest(BaseModel):
    """Request to copy the pending session onto a date."""

    date: str = Field(..., description="Target date in YYYY-MM-DD format")


class MobilityTransferResponse(BaseModel):
    """Response from copying the pending session into the calendar."""

    date: str
    count: int
    message: str
