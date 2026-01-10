"""Upcoming workout API endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.models.upcoming import (
    LiftoscriptGenerateRequest,
    LiftoscriptGenerateResponse,
    PresetContent,
    PresetInfo,
    SessionTransferRequest,
    SessionTransferResponse,
    UpcomingWorkout,
    UpcomingWorkoutBulkCreate,
    UpcomingWorkoutCreate,
    WendlerCurrentMaxes,
)
from app.models.workout import WorkoutCreate
from app.repositories.upcoming_repo import UpcomingWorkoutRepository
from app.repositories.workout_repo import WorkoutRepository
from app.services.liftoscript_service import LiftoscriptParseError, LiftoscriptParser
from app.services.wendler_service import WendlerService

# Available presets with metadata
PRESETS = {
    "wendler_531": {
        "display_name": "Wendler 5/3/1",
        "description": "Classic 4-week strength program with 3 training days per week. Includes squat, bench, and deadlift progression with accessories.",
    },
}

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
            exercise=upcoming_workout["exercise"],
            category=upcoming_workout["category"],
            weight=upcoming_workout.get("weight"),
            weight_unit=upcoming_workout.get("weight_unit", "lbs"),
            reps=upcoming_workout.get("reps"),
            distance=upcoming_workout.get("distance"),
            distance_unit=upcoming_workout.get("distance_unit"),
            time=upcoming_workout.get("time"),
            comment=upcoming_workout.get("comment"),
            order=i + 1,
        )
        workout_repo.create(historical_workout)

    # Delete the session from upcoming
    count = upcoming_repo.delete_session(session)

    return SessionTransferResponse(
        session=session,
        date=request.date,
        count=count,
        message=f"Transferred {count} workouts to {request.date}",
    )


@router.get("/wendler/maxes", response_model=WendlerCurrentMaxes)
def get_wendler_current_maxes():
    """Get current estimated 1RM values for main lifts."""
    service = WendlerService()
    maxes = service.get_current_maxes()

    return WendlerCurrentMaxes(
        squat=maxes.get("Barbell Squat"),
        bench=maxes.get("Flat Barbell Bench Press"),
        deadlift=maxes.get("Deadlift"),
    )


@router.post("/liftoscript/generate", response_model=LiftoscriptGenerateResponse)
def generate_liftoscript_workouts(request: LiftoscriptGenerateRequest):
    """Generate upcoming workouts from Liftoscript program.

    Supports simplified syntax:
    - ## Day Name headers to separate sessions
    - Exercise Name / sets x reps weight
    - Comments via // (required for % and progress: lp())
    - Weight formats: "135lb", "60kg", "65%", "progress: lp(5lb)"

    Required comments for percentage/progression:
    - For %: "// ExerciseName 1RM: Xlb"
    - For progress: lp(): "// ExerciseName SW: Xlb" (SW = Starting Weight)
    """
    repo = UpcomingWorkoutRepository()

    parser = LiftoscriptParser()
    try:
        workouts = parser.parse(
            script=request.script,
            num_cycles=request.num_cycles,
        )
    except LiftoscriptParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse script: {str(e)}")

    if not workouts:
        return LiftoscriptGenerateResponse(
            success=False,
            message="No workouts generated from script",
            count=0,
            sessions=0,
            deleted_count=0,
        )

    deleted_count = repo.delete_all()
    created = repo.create_bulk(workouts)
    sessions = len(set(w.session for w in workouts))

    return LiftoscriptGenerateResponse(
        success=True,
        message=f"Generated {len(created)} workouts across {sessions} sessions",
        count=len(created),
        sessions=sessions,
        deleted_count=deleted_count,
    )


@router.get("/presets", response_model=list[PresetInfo])
def get_presets():
    """Get list of available workout program presets."""
    return [
        PresetInfo(
            name=name,
            display_name=data["display_name"],
            description=data["description"],
        )
        for name, data in PRESETS.items()
    ]


@router.get("/presets/{name}", response_model=PresetContent)
def get_preset(name: str):
    """Get a specific preset by name."""
    if name not in PRESETS:
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")

    # Read the preset file
    preset_dir = Path(__file__).parent.parent / "presets"
    preset_file = preset_dir / f"{name}.liftoscript"

    if not preset_file.exists():
        raise HTTPException(status_code=404, detail=f"Preset file '{name}' not found")

    script = preset_file.read_text()

    return PresetContent(
        name=name,
        display_name=PRESETS[name]["display_name"],
        script=script,
    )
