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
    """The last mobility session that reached the calendar.

    `rationale` is **nullable, and usually null**. It exists only when a plan
    note was promoted at transfer, which means the agent prescribed the
    session; a day whose sets the user flagged by hand has no note and never
    will, because nothing prescribed it and an invented rationale would read as
    an instruction that was tried.

    This was non-optional until 2026-08-19 and it 500'd the whole endpoint the
    first time a hand-flagged day became the last session — which, since the
    flag moved to the set (0013), is the ordinary case rather than the exotic
    one.
    """

    date: str
    rationale: str | None = None
    sets: list[MobilityLoggedSet]


class MobilityPendingSession(BaseModel):
    """One pending session: what it is called, why, and what is in it."""

    session: int
    #: The addressing key the agent writes against, and what the user reads on
    #: the page to tell "Low back" from "Shoulder".
    label: str
    rationale: str
    generated_at: str
    items: list[UpcomingWorkout] = Field(default_factory=list)


class MobilityPending(BaseModel):
    """What the mobility tab renders.

    `ready` is still derived and still the state discriminator, but it now
    means *any* session is pending. There is no 'generating' state: the agent
    writes a session in one transaction over MCP, so from the page's point of
    view a session either exists or does not.

    `sessions` replaced a single flattened routine when rehabbing two areas at
    once made one pending prescription untenable (b6f31a90c4de). A session with
    no items is omitted rather than shown empty.

    `last_session` is present in every state on purpose. When nothing is
    pending it is what makes the empty state actionable, because it carries the
    comments the next session has to be written from.
    """

    ready: bool
    sessions: list[MobilityPendingSession] = Field(default_factory=list)
    last_session: MobilityLastSession | None = None

    model_config = ConfigDict(populate_by_name=True)


class MobilityTransferRequest(BaseModel):
    """Request to copy one pending session onto a date.

    `session` names which — the page lists several and the user picks.
    """

    session: int
    date: str = Field(..., description="Target date in YYYY-MM-DD format")


class MobilityTransferResponse(BaseModel):
    """Response from copying one pending session into the calendar."""

    date: str
    count: int
    #: Which session moved. None only when nothing matched the request.
    label: str | None = None
    message: str
