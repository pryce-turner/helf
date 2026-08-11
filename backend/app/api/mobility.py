"""Mobility session API endpoints.

Deliberately small. There is no create endpoint here: the pending session is
written by the agent over MCP (`write_next_mobility_session`), and the whole
point of the feature is that the prescription is reasoned about rather than
typed in. What the app does is show it and move it onto a date.
"""

from fastapi import APIRouter, HTTPException

from app.models.mobility import (
    MobilityPending,
    MobilityTransferRequest,
    MobilityTransferResponse,
)
from app.services.mobility_service import MobilityService

router = APIRouter()


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
