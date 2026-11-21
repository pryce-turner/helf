"""Mobility API endpoints: the shuffle, the read-back, and the agent's write.

The queue half of mobility is gone (9c4e7b21f806): pending sessions are listed,
transferred and discarded through the upcoming routes, because that is what
they are — upcoming workouts. What stays here is what the upcoming routes know
nothing about:

`POST /suggest` inserts a shuffled movement-break tile on a date.

`GET /last-session` reads the last mobility session that was run, with the
comments on its sets — the feedback channel the next prescription is written
from.

`POST /pending` is the one write, and it is not a form for typing a routine in
- the prescription is still reasoned about by the agent, and MCP
(`write_next_mobility_session`) is still the primary path. It exists because
the MCP server opens `data/helf.db` from whatever process the agent runs in, so
a filesystem permission mismatch on the database (uid 3000 against a tree owned
by 568) can block the agent's write entirely. This endpoint writes through the
app process, which owns the database, and does exactly what the tool does:
upsert the plan by label, replace that session's rows, one row per set, no
per-set comment.

There is no endpoint here for marking a day either. Which sets were mobility
work is a field on the set, written through the normal workout routes, and the
day follows from them (d7e4f2a91b83).
"""

from fastapi import APIRouter, HTTPException

from app.models.mobility import (
    MobilityLastSession,
    MobilityPendingWrite,
    MobilityPendingWriteResponse,
    MovementBreakSuggest,
)
from app.models.workout import Workout
from app.services.mobility_service import MobilityService

router = APIRouter()


@router.get("/last-session", response_model=MobilityLastSession | None)
def get_last_session():
    """The last mobility session that reached the calendar, with its sets.

    None when no set has ever been flagged — the upcoming page renders its
    empty state from that.
    """
    return MobilityService().get_last_session()


@router.post("/pending", response_model=MobilityPendingWriteResponse)
def write_pending_session(request: MobilityPendingWrite):
    """Write a pending session under `label`, creating it or replacing that one."""
    return MobilityService().write_pending(
        request.label,
        request.rationale,
        [item.model_dump() for item in request.items],
    )


@router.post("/suggest", response_model=Workout, status_code=201)
def suggest_movement_break(request: MovementBreakSuggest):
    """Insert a suggested, incomplete mobility tile on the date.

    The tile is the shuffle's pick with the movement's own defaults applied —
    editable and deletable like any planned tile, and not logged as performed
    until it is played. This replaced the old finished-run writer (plan
    0018): nothing here creates completed rows, so a double tap at worst
    suggests twice, and the button that calls it disables while pending.
    """
    tile = MobilityService().suggest_movement_break(request.date)

    if tile is None:
        raise HTTPException(
            status_code=404, detail="No movements in the movement break pool"
        )

    return tile
