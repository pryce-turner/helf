"""Upcoming workout API endpoints.

The queue is one program (9c4e7b21f806): Liftoscript-generated sessions and
agent-written mobility sessions list together, and transfer, delete and
generate treat them alike. What still differs by author is metadata, not
behaviour — an agent session carries the label and rationale `mobility_plan`
holds, and transferring one promotes that rationale into a dated note so the
next prescription can read why the last one was written.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.models.upcoming import (
    LiftoscriptGenerateRequest,
    LiftoscriptGenerateResponse,
    LiftoscriptProgram,
    PresetContent,
    PresetInfo,
    SessionTransferRequest,
    SessionTransferResponse,
    UpcomingSession,
    UpcomingWorkout,
    UpcomingWorkoutBulkCreate,
    UpcomingWorkoutCreate,
    WendlerCurrentMaxes,
)
from app.models.workout import WorkoutCreate
from app.repositories.mobility_repo import MobilityRepository
from app.repositories.upcoming_repo import UpcomingWorkoutRepository
from app.repositories.workout_repo import WorkoutRepository
from app.services.library_service import resolve_block
from app.services.liftoscript_service import LiftoscriptParseError, LiftoscriptParser
from app.services.wendler_service import WendlerService
from app.utils.durations import parse_duration_seconds

# Available presets with metadata
PRESETS = {
    "wendler_531": {
        "display_name": "Wendler 5/3/1",
        "description": "Classic 4-week strength program with 3 training days per week. Includes squat, bench, and deadlift progression with accessories.",
    },
    "stronglifts_5x5": {
        "display_name": "StrongLifts 5x5",
        "description": "Simple but effective strength program focusing on 5 sets of 5 reps on the big three lifts.",
    },
    "cutting_rotation": {
        "display_name": "Cutting Rotation",
        "description": "Minimalist 3-workout rotation (Squat/Bench/Deadlift) for cutting. One main lift per session with light accessories. Rotate A→B→C regardless of schedule.",
    },
    "core_stability_531": {
        "display_name": "5/3/1 Core Stability",
        "description": "Four-day 5/3/1 (press, deadlift, bench, squat) over four weeks with a deload, each day framed by dynamic stretching, a two-movement core-stability block, accessories, foam rolling and static stretching. The 1RM lines are training maxes.",
    },
}

router = APIRouter()


@router.get("/", response_model=list[UpcomingSession])
def get_upcoming_workouts():
    """Get the whole upcoming queue, grouped by session.

    Agent-written sessions carry the label, rationale and write date their
    `mobility_plan` row holds; Liftoscript sessions have none. A plan whose
    rows are all gone is omitted rather than shown as an empty heading.
    """
    rows = UpcomingWorkoutRepository().get_all()
    plans = {plan["session"]: plan for plan in MobilityRepository().get_plans()}

    sessions: dict[int, UpcomingSession] = {}
    for row in rows:
        number = row["session"]
        if number not in sessions:
            plan = plans.get(number)
            sessions[number] = UpcomingSession(
                session=number,
                label=plan["label"] if plan else None,
                rationale=plan["rationale"] if plan else None,
                generated_at=plan["generated_at"] if plan else None,
            )
        sessions[number].items.append(UpcomingWorkout(**row))

    return [sessions[number] for number in sorted(sessions)]


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
    """Delete a session: its rows, and its plan if it has one.

    Both halves go together. Leaving the plan behind would lend its label and
    rationale to whatever session is numbered the same later, and leaving the
    rows behind would orphan them under a heading nothing renders.
    """
    repo = UpcomingWorkoutRepository()
    count = repo.delete_session(session)

    if count == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    MobilityRepository().delete_plan(session)


@router.post("/session/{session}/transfer", response_model=SessionTransferResponse)
def transfer_session(session: int, request: SessionTransferRequest):
    """Transfer a session to historical workouts.

    Rows are appended **after** anything already logged that day rather than
    numbered from 1, so transferring a second session onto the same date
    stacks under the first. Each row's `is_mobility` travels with it — the
    prescription said which sets were mobility work, and the logged day keeps
    it (the day-view checkbox can still adjust).

    A session with a plan is the agent's: its rationale is promoted into a
    dated `mobility_session` note, which is what
    `read_latest_mobility_session` reports back as *why* the session was
    written. The plan row goes with the promotion — it described a pending
    session, and the session is no longer pending.
    """
    upcoming_repo = UpcomingWorkoutRepository()
    workout_repo = WorkoutRepository()
    mobility_repo = MobilityRepository()

    # Get all workouts in the session
    session_workouts = upcoming_repo.get_by_session(session)

    if not session_workouts:
        raise HTTPException(status_code=404, detail="Session not found")

    existing = workout_repo.get_by_date(request.date)
    start_order = max((w.get("order") or 0) for w in existing) if existing else 0

    # Transfer each workout to historical
    for offset, upcoming_workout in enumerate(session_workouts, start=1):
        historical_workout = WorkoutCreate(
            date=request.date,
            exercise=upcoming_workout["exercise"],
            category=upcoming_workout["category"],
            weight=upcoming_workout.get("weight"),
            weight_unit=upcoming_workout.get("weight_unit", "lbs"),
            reps=upcoming_workout.get("reps"),
            distance=upcoming_workout.get("distance"),
            distance_unit=upcoming_workout.get("distance_unit"),
            # The planned timing travels field for field (842c1976c18a). A
            # row from before it may hold only the legacy `time`, read-only
            # since plan 0018; its duration moves onto the tile as
            # `work_seconds` rather than dropping.
            work_seconds=(
                upcoming_workout.get("work_seconds")
                if upcoming_workout.get("work_seconds") is not None
                else parse_duration_seconds(upcoming_workout.get("time"))
            ),
            rest_seconds=upcoming_workout.get("rest_seconds"),
            rest_after_seconds=upcoming_workout.get("rest_after_seconds"),
            comment=upcoming_workout.get("comment"),
            order=start_order + offset,
            is_mobility=upcoming_workout.get("is_mobility", False),
        )
        workout_repo.create(historical_workout)

    # Delete the session from upcoming
    count = upcoming_repo.delete_session(session)

    # Promote the plan's rationale into the record of a session run. A
    # Liftoscript session has no plan, and the call returns None for it.
    plan = mobility_repo.get_plan(session)
    mobility_repo.record_session_note(session, request.date)

    label = plan["label"] if plan else None
    what = f"'{label}'" if label else f"session {session}"
    return SessionTransferResponse(
        session=session,
        date=request.date,
        count=count,
        label=label,
        message=f"Transferred {count} sets from {what} to {request.date}",
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


@router.get("/liftoscript/last", response_model=LiftoscriptProgram | None)
def get_last_liftoscript_program():
    """The script and cycle count the last successful generate ran, or null."""
    return UpcomingWorkoutRepository().last_program()


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

    Generating clears the **whole** queue first — rows and plans alike. The
    kind-scoped delete used to spare the pending mobility session; with one
    queue the guard is the warning the page shows before confirming
    (9c4e7b21f806).
    """
    repo = UpcomingWorkoutRepository()
    mobility_repo = MobilityRepository()

    parser = LiftoscriptParser()
    try:
        workouts = parser.parse(
            script=request.script,
            num_cycles=request.num_cycles,
            # `[Block]` lines: built-in blocks, then yours (plan 0022).
            resolve_block=resolve_block,
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

    # Before anything is cleared: a program whose timing or distance would be
    # dropped at transfer is refused whole, with the fix named.
    turned_off = repo.groups_turned_off(workouts)
    if turned_off:
        raise HTTPException(
            status_code=400,
            detail=(
                "; ".join(turned_off)
                + ". Turn it on for the exercise on the Exercises page, or take "
                "the timing or distance out of the script."
            ),
        )

    deleted_count = repo.delete_all()
    deleted_plans = mobility_repo.delete_all_plans()
    created = repo.create_bulk(workouts)
    sessions = len(set(w.session for w in workouts))
    # Only a program that produced a queue is kept: a script that failed to
    # parse, or generated nothing, never reaches this line.
    repo.save_program(request.script, request.num_cycles)

    message = f"Generated {len(created)} workouts across {sessions} sessions"
    if deleted_plans:
        message += f"; replaced {deleted_plans} agent-written session(s)"
    return LiftoscriptGenerateResponse(
        success=True,
        message=message,
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
