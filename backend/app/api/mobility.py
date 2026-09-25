"""Mobility session API endpoints.

Deliberately small: show the pending sessions, move one onto a date, discard
one, and write one.

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
    MobilityPending,
    MobilityPendingWrite,
    MobilityPendingWriteResponse,
    MobilityTransferRequest,
    MobilityTransferResponse,
)
from app.services.mobility_service import MobilityService

router = APIRouter()

@router.get("/pending", response_model=MobilityPending)
def get_pending_session():
    """The pending mobility session, or what to do about there not being one."""
    return MobilityService().get_pending()


@router.post("/pending", response_model=MobilityPendingWriteResponse)
def write_pending_session(request: MobilityPendingWrite):
    """Write a pending session under `label`, creating it or replacing that one."""
    return MobilityService().write_pending(
        request.label,
        request.rationale,
        [item.model_dump() for item in request.items],
    )


@router.post("/transfer", response_model=MobilityTransferResponse)
def transfer_pending_session(request: MobilityTransferRequest):
    """Copy the pending session into the calendar on a date."""
    result = MobilityService().transfer(request.date, request.session)

    if result["count"] == 0:
        raise HTTPException(status_code=404, detail="No pending mobility session")

    return MobilityTransferResponse(**result)


@router.delete("/pending/{session}", status_code=204)
def clear_pending_session(session: int):
    """Discard one pending session without running it.

    Takes a session because several can be pending: rehabbing a low back and a
    shoulder at once means two prescriptions alive, and discarding one must
    leave the other where it is.
    """
    if MobilityService().clear_pending(session) == 0:
        raise HTTPException(status_code=404, detail="No such pending mobility session")
