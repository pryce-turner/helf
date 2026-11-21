"""Mobility schemas — the HTTP contract for the mobility endpoints.

What the upcoming routes already say is not repeated here (9c4e7b21f806): a
pending session is an upcoming session, and listing, transferring and
discarding one are answered there. These are the shapes that remain — the
last session that was run, the movement-break shuffle, and the agent's write.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MobilityLoggedSet(BaseModel):
    """One set tile as it was logged: targets beside what was performed.

    The actuals are NULL until the tile is performed (plan 0018). A planned
    tile is not work yet; a stopped one keeps `ended_early` set so the next
    prescription reads the shortfall rather than the target as the result.
    """

    exercise: str
    weight: float | None = None
    reps: int | None = None
    time: str | None = None
    comment: str | None = None
    order: int
    completed: bool = False
    work_seconds: int | None = None
    rest_seconds: int | None = None
    rest_after_seconds: int | None = None
    completed_reps: int | None = None
    actual_work_seconds: float | None = None
    actual_rest_seconds: float | None = None
    actual_rest_after_seconds: float | None = None
    ended_early: bool = False


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


class MovementBreakSuggest(BaseModel):
    """Ask for a movement break suggestion on a day.

    The answer is an ordinary planned tile on that date holding the
    shuffled movement's field defaults — not a finished run. The old
    `POST /movement-break` wrote one completed row per interval; the
    suggestion counts as nothing until it is played (plan 0018).
    """

    #: Defaults to today, in the app's timezone — never the client's guess.
    date: str | None = Field(
        None, description="Target date in YYYY-MM-DD format; today when omitted"
    )


class MobilityPendingItemWrite(BaseModel):
    """One movement in a session being written: `sets` identical rows of it.

    `extra="forbid"` because a misspelt key is the likely mistake here, and
    ignoring it is the dangerous response: `weight` for `weight_lb` would
    otherwise write a session with every load silently missing.
    """

    model_config = ConfigDict(extra="forbid")

    exercise: str = Field(..., min_length=1)
    sets: int = Field(1, ge=1)
    reps: int | None = None
    #: Pounds (ADR-0003).
    weight_lb: float | None = None
    #: Only places a movement created by this write; ignored for one that exists.
    category: str | None = None
    #: Whether the movement's rows are mobility work. Defaults True — this
    #: writer is the mobility loop — but a session can prescribe unflagged
    #: sets alongside the mobility element.
    mobility: bool = True
    #: Accepted only as null, so the refusal can say where the text belongs.
    comment: None = None

    @field_validator("comment", mode="before")
    @classmethod
    def refuse_comment(cls, value):
        if value is not None:
            raise ValueError(
                "prescribed sets carry no comment - that field is the user's "
                "feedback channel, and text left in it reads back as something "
                "they said. Put the cue, the load and what changed in "
                "`rationale` instead."
            )
        return value


class MobilityPendingWrite(BaseModel):
    """Request to write a pending session under `label`, creating or replacing it.

    The same contract as the MCP tool `write_next_mobility_session`.
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    rationale: str
    items: list[MobilityPendingItemWrite] = Field(..., min_length=1)

    @field_validator("label", "rationale")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class MobilityPendingWriteResponse(BaseModel):
    """What a write did. Mirrors the MCP tool's result, minus `ok`."""

    label: str
    session: int
    sets_written: int
    movements: int
    replaced_pending_rows: int
    exercises_created: list[str]
