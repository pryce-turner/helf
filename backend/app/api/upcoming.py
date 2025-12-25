"""Upcoming workout API endpoints."""

from fastapi import APIRouter, HTTPException

from app.models.upcoming import (
    UpcomingWorkout,
    UpcomingWorkoutCreate,
    UpcomingWorkoutBulkCreate,
    SessionTransferRequest,
    SessionTransferResponse,
)
from app.models.workout import WorkoutCreate
from app.repositories.upcoming_repo import UpcomingWorkoutRepository
from app.repositories.workout_repo import WorkoutRepository

router = APIRouter()


@router.get("/", response_model=list[UpcomingWorkout])
def get_upcoming_workouts():
    """Get all upcoming workouts."""
    repo = UpcomingWorkoutRepository()
    return repo.get_all()


@router.get("/session/{session}", response_model=list[UpcomingWorkout])
def get_session(session: int):
    """Get all workouts for a specific session."""
    repo = UpcomingWorkoutRepository()
    workouts = repo.get_by_session(session)

    if not workouts:
        raise HTTPException(status_code=404, detail="Session not found")

    return workouts


@router.post("/", response_model=UpcomingWorkout, status_code=201)
def create_upcoming_workout(workout: UpcomingWorkoutCreate):
    """Create a new upcoming workout."""
    repo = UpcomingWorkoutRepository()
    return repo.create(workout)


@router.post("/bulk", response_model=list[UpcomingWorkout], status_code=201)
def create_bulk_upcoming_workouts(bulk: UpcomingWorkoutBulkCreate):
    """Create multiple upcoming workouts."""
    repo = UpcomingWorkoutRepository()
    return repo.create_bulk(bulk.workouts)


@router.delete("/session/{session}", status_code=204)
def delete_session(session: int):
    """Delete all workouts in a session."""
    repo = UpcomingWorkoutRepository()
    count = repo.delete_session(session)

    if count == 0:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/session/{session}/transfer", response_model=SessionTransferResponse)
def transfer_session(session: int, request: SessionTransferRequest):
    """Transfer a session to historical workouts."""
    upcoming_repo = UpcomingWorkoutRepository()
    workout_repo = WorkoutRepository()

    # Get all workouts in the session
    session_workouts = upcoming_repo.get_by_session(session)

    if not session_workouts:
        raise HTTPException(status_code=404, detail="Session not found")

    # Transfer each workout to historical
    for i, upcoming_workout in enumerate(session_workouts):
        historical_workout = WorkoutCreate(
            date=request.date,
            exercise=upcoming_workout['exercise'],
            category=upcoming_workout['category'],
            weight=upcoming_workout.get('weight'),
            weight_unit=upcoming_workout.get('weight_unit', 'lbs'),
            reps=upcoming_workout.get('reps'),
            distance=upcoming_workout.get('distance'),
            distance_unit=upcoming_workout.get('distance_unit'),
            time=upcoming_workout.get('time'),
            comment=upcoming_workout.get('comment'),
            order=i + 1,
        )
        workout_repo.create(historical_workout)

    # Delete the session from upcoming
    count = upcoming_repo.delete_session(session)

    return SessionTransferResponse(
        session=session,
        date=request.date,
        count=count,
        message=f"Transferred {count} workouts to {request.date}"
    )
