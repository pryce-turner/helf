"""Workout API endpoints."""


from fastapi import APIRouter, HTTPException
from fastapi import Query as QueryParam

from app.models.workout import (
    CalendarResponse,
    Workout,
    WorkoutBulkReorder,
    WorkoutComplete,
    WorkoutCopyDate,
    WorkoutDayMobility,
    WorkoutDayMobilityResponse,
    WorkoutCopyDateResponse,
    WorkoutCreate,
    WorkoutMoveDate,
    WorkoutMoveDateResponse,
    WorkoutUpdate,
)
from app.repositories.workout_repo import WorkoutRepository

router = APIRouter()


@router.get("/", response_model=list[Workout])
def get_workouts(
    date: str | None = None,
    skip: int = 0,
    limit: int = 100,
):
    """Get workouts, optionally filtered by date."""
    repo = WorkoutRepository()

    if date:
        workouts = repo.get_by_date(date)
        return workouts

    return repo.get_all(skip=skip, limit=limit)


@router.get("/calendar", response_model=CalendarResponse)
def get_calendar(
    year: int = QueryParam(..., description="Year"),
    month: int = QueryParam(..., ge=1, le=12, description="Month (1-12)"),
):
    """Get workout counts by date for calendar view."""
    repo = WorkoutRepository()
    counts = repo.get_workout_counts_by_date(year, month)

    return CalendarResponse(year=year, month=month, counts=counts)


@router.get("/{workout_id}", response_model=Workout)
def get_workout(workout_id: int):
    """Get a specific workout by ID."""
    repo = WorkoutRepository()
    workout = repo.get_by_id(workout_id)

    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    return workout


@router.post("/", response_model=Workout, status_code=201)
def create_workout(workout: WorkoutCreate):
    """Create a new workout."""
    repo = WorkoutRepository()
    return repo.create(workout)


@router.put("/{workout_id}", response_model=Workout)
def update_workout(workout_id: int, workout: WorkoutUpdate):
    """Update an existing workout."""
    repo = WorkoutRepository()
    updated = repo.update(workout_id, workout)

    if not updated:
        raise HTTPException(status_code=404, detail="Workout not found")

    return updated


@router.delete("/{workout_id}", status_code=204)
def delete_workout(workout_id: int):
    """Delete a workout."""
    repo = WorkoutRepository()
    deleted = repo.delete(workout_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Workout not found")


@router.patch("/reorder")
def bulk_reorder_workouts(reorder: WorkoutBulkReorder):
    """Bulk reorder workouts by providing ordered list of IDs."""
    repo = WorkoutRepository()
    success = repo.bulk_reorder(reorder.workout_ids)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to reorder workouts")

    return {"success": True, "message": "Workouts reordered"}


@router.post("/date/{source_date}/move", response_model=WorkoutMoveDateResponse)
def move_workouts_to_date(source_date: str, move: WorkoutMoveDate):
    """Move all workouts from one date to another."""
    repo = WorkoutRepository()

    if source_date == move.target_date:
        raise HTTPException(status_code=400, detail="Source and target dates must be different")

    count = repo.move_to_date(source_date, move.target_date)

    if count == 0:
        raise HTTPException(status_code=404, detail="No workouts found on source date")

    return WorkoutMoveDateResponse(
        source_date=source_date,
        target_date=move.target_date,
        count=count,
        message=f"Moved {count} workout(s) to {move.target_date}"
    )


@router.patch(
    "/date/{date}/mobility", response_model=WorkoutDayMobilityResponse
)
def set_day_mobility(date: str, update: WorkoutDayMobility):
    """Flag every set on a day as mobility work, or clear every one.

    A convenience over the per-set flag, not a day-level marker: it writes the
    same `workouts.is_mobility` the per-set toggle writes, and nothing is
    stored about the day itself (plan 0013 §6). A day whose sets disagree stays
    a valid state — this endpoint just does not produce one.

    PATCH, and idempotent: the caller is a button that knows the state it
    wants. Sending the state a day is already in reports `changed: 0` rather
    than failing, because pressing it twice has to mean what pressing it once
    meant.

    No date pattern check, unlike the marker endpoint this replaces. That one
    *created* a row keyed by the date, so a malformed one became a permanent
    artifact; this one only ever matches existing rows, and a date that matches
    nothing is a 404.
    """
    changed, total = WorkoutRepository().set_mobility_for_date(
        date, update.is_mobility
    )

    if total == 0:
        raise HTTPException(status_code=404, detail=f"No workouts logged on {date}")

    verb = "Marked" if update.is_mobility else "Unmarked"
    return WorkoutDayMobilityResponse(
        date=date,
        is_mobility=update.is_mobility,
        changed=changed,
        total=total,
        message=f"{verb} {changed} of {total} set(s) on {date}",
    )


@router.post("/date/{source_date}/copy", response_model=WorkoutCopyDateResponse)
def copy_workouts_to_date(source_date: str, copy: WorkoutCopyDate):
    """Copy all workouts from one date to another."""
    repo = WorkoutRepository()

    if source_date == copy.target_date:
        raise HTTPException(
            status_code=400,
            detail="Source and target dates must be different"
        )

    count = repo.copy_to_date(source_date, copy.target_date)

    if count == 0:
        raise HTTPException(
            status_code=404,
            detail="No workouts found on source date"
        )

    return WorkoutCopyDateResponse(
        source_date=source_date,
        target_date=copy.target_date,
        count=count,
        message=f"Successfully copied {count} workout(s) from {source_date} to {copy.target_date}"
    )


@router.patch("/{workout_id}/complete", response_model=Workout)
def toggle_workout_complete(workout_id: int, complete: WorkoutComplete):
    """Mark a workout set as complete or incomplete."""
    repo = WorkoutRepository()

    updated = repo.toggle_complete(workout_id, complete.completed)

    if not updated:
        raise HTTPException(status_code=404, detail="Workout not found")

    return updated
