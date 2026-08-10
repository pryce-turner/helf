"""Stack API endpoints — preset groups of consumables."""

from fastapi import APIRouter, HTTPException

from app.models.stack import (
    Stack,
    StackCreate,
    StackLogRequest,
    StackLogResult,
    StackUpdate,
)
from app.repositories.stack_repo import StackRepository

router = APIRouter()


@router.get("/", response_model=list[Stack])
def get_stacks():
    """All stacks, with whether each has been taken today."""
    return StackRepository().get_all()


@router.post("/", response_model=Stack, status_code=201)
def create_stack(payload: StackCreate):
    """Create a stack. Items naming a food that is not in the catalog create it."""
    try:
        return StackRepository().create(payload)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{stack_id}", response_model=Stack)
def get_stack(stack_id: int):
    """Get one stack."""
    stack = StackRepository().get_by_id(stack_id)
    if stack is None:
        raise HTTPException(status_code=404, detail="Stack not found")
    return stack


@router.put("/{stack_id}", response_model=Stack)
def update_stack(stack_id: int, changes: StackUpdate):
    """Edit a stack. Sending `items` replaces the membership wholesale."""
    try:
        updated = StackRepository().update(stack_id, changes)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Stack not found")
    return updated


@router.delete("/{stack_id}")
def delete_stack(stack_id: int):
    """Delete a stack. Past log entries and the foods themselves are untouched."""
    if not StackRepository().delete(stack_id):
        raise HTTPException(status_code=404, detail="Stack not found")
    return {"message": "Stack deleted"}


@router.post("/{stack_id}/log", response_model=StackLogResult, status_code=201)
def log_stack(stack_id: int, payload: StackLogRequest | None = None):
    """Log every item in the stack at one instant."""
    logged = StackRepository().log(
        stack_id, payload.consumed_at if payload else None
    )
    if logged is None:
        raise HTTPException(status_code=404, detail="Stack not found")
    if not logged["entries"]:
        raise HTTPException(
            status_code=422,
            detail="This stack has no items, so there is nothing to log.",
        )
    return logged
