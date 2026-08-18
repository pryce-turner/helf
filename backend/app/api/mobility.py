"""Mobility session API endpoints.

Deliberately small. There is no create endpoint here: the pending session is
written by the agent over MCP (`write_next_mobility_session`), and the whole
point of the feature is that the prescription is reasoned about rather than
typed in. What the app does is show it, move it onto a date, and say which days
were mobility days - that last one because the marker is what the agent reads
the next session back from, and a session run without the planner would
otherwise leave nothing to read.
"""

from fastapi import APIRouter, HTTPException, Path

from app.models.mobility import (
    MobilityDay,
    MobilityDayUpdate,
    MobilityPending,
    MobilityTransferRequest,
    MobilityTransferResponse,
)
from app.services.mobility_service import MobilityService

router = APIRouter()

#: The date is the note's `noted_at` and, through it, the computed `date` the
#: agent reads back. Validated in the path rather than trusted, because a
#: malformed one is not rejected downstream - it becomes a marker note dated
#: to nonsense, which sorts *after* every real date and would be handed to the
#: agent as the last session performed.
DatePath = Path(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")


@router.get("/pending", response_model=MobilityPending)
def get_pending_session():
    """The pending mobility session, or what to do about there not being one."""
    return MobilityService().get_pending()


@router.post("/transfer", response_model=MobilityTransferResponse)
def transfer_pending_session(request: MobilityTransferRequest):
    """Copy the pending session into the calendar on a date."""
    result = MobilityService().transfer(request.date)

    if result["count"] == 0:
        raise HTTPException(status_code=404, detail="No pending mobility session")

    return MobilityTransferResponse(**result)


@router.delete("/pending", status_code=204)
def clear_pending_session():
    """Discard the pending session without running it."""
    if MobilityService().clear_pending() == 0:
        raise HTTPException(status_code=404, detail="No pending mobility session")


@router.get("/day/{date}", response_model=MobilityDay)
def get_day(date: str = DatePath):
    """Whether a day is marked as a mobility session."""
    return MobilityService().get_day(date)


@router.put("/day/{date}", response_model=MobilityDay)
def set_day(update: MobilityDayUpdate, date: str = DatePath):
    """Mark or unmark a day as a mobility session.

    PUT rather than POST/DELETE because the caller is a checkbox: it knows the
    state it wants, not the transition, and sending the same state twice has to
    mean the same thing both times.
    """
    return MobilityService().set_day(date, update.is_mobility)
