"""Progression API endpoints."""

from fastapi import APIRouter, Query as QueryParam

from app.models.progression import ProgressionResponse
from app.services.progression_service import ProgressionService
from app.repositories.exercise_repo import ExerciseRepository

router = APIRouter()


@router.get("/{exercise}", response_model=ProgressionResponse)
def get_progression(
    exercise: str,
    include_upcoming: bool = QueryParam(True, description="Include upcoming workouts"),
):
    """Get progression data for a specific exercise."""
    service = ProgressionService()
    return service.get_progression_data(exercise, include_upcoming=include_upcoming)


@router.get("/", response_model=dict)
def get_main_lifts():
    """Get progression data for main 3 lifts."""
    service = ProgressionService()
    return service.get_main_lifts_progression()


@router.get("/exercises/list", response_model=list[str])
def get_exercise_list():
    """Get list of all exercises for progression tracking."""
    repo = ExerciseRepository()
    exercises = repo.get_all()
    return [e['name'] for e in exercises]
