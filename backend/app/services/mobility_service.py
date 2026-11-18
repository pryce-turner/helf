"""The mobility loop: read the pending session, and copy it into the calendar.

The loop has four steps and only two of them are code. The agent reads the last
logged session over MCP and writes the next one; this module is the other half
— it shows the user what is pending and moves it onto a date when they run it.
"""

from app.models.workout import WorkoutCreate
from app.repositories.exercise_repo import ExerciseRepository
from app.repositories.mobility_repo import MobilityRepository
from app.repositories.upcoming_repo import (
    MOBILITY,
    UpcomingWorkoutRepository,
)
from app.repositories.workout_repo import WorkoutRepository
from app.utils.date_helpers import get_current_date, get_current_datetime


class MobilityService:
    """Orchestrates the three tables a mobility session touches."""

    def __init__(self) -> None:
        self.upcoming_repo = UpcomingWorkoutRepository()
        self.workout_repo = WorkoutRepository()
        self.mobility_repo = MobilityRepository()
        self.exercise_repo = ExerciseRepository()

    def get_pending(self) -> dict:
        """Every pending session, and the last one that was run.

        `ready` is still derived and still the page's discriminator, but it now
        means "any session is pending" rather than "the session is pending".
        Each entry carries its own label, reasoning and movements, because the
        page's job changed from showing one routine to choosing between
        several.
        """
        plans = self.mobility_repo.get_plans()

        sessions = []
        for plan in plans:
            items = self.upcoming_repo.get_by_session(plan["session"], kind=MOBILITY)
            # A plan whose rows have all been deleted is a heading with nothing
            # under it. Skipped rather than shown empty, the same way a
            # rationale with no items was never reported.
            if not items:
                continue
            sessions.append({**plan, "items": items})

        return {
            "ready": bool(sessions),
            "sessions": sessions,
            "last_session": self.mobility_repo.get_latest_logged(),
        }

    def write_pending(self, label: str, rationale: str, items: list[dict]) -> dict:
        """Write one pending session under `label`. See `MobilityRepository.write_session`."""
        return self.mobility_repo.write_session(label, rationale, items)

    def transfer(self, date: str, session_id: int) -> dict:
        """Copy one pending session onto `date` as mobility sets.

        Which session is now an argument: the page lists several and the user
        picks. Rows are appended **after** anything already logged that day, so
        transferring a second session onto the same date stacks under the
        first rather than interleaving — two prescriptions run back to back are
        still two sessions' work in one day.

        Each row is written with `is_mobility = True`, which is what makes the
        day findable afterwards (0013).
        """
        plan = self.mobility_repo.get_plan(session_id)
        items = self.upcoming_repo.get_by_session(session_id, kind=MOBILITY)
        if not plan or not items:
            return {"date": date, "count": 0, "message": "No such pending session"}

        existing = self.workout_repo.get_by_date(date)
        start_order = max((w.get("order") or 0) for w in existing) if existing else 0

        for offset, item in enumerate(items, start=1):
            self.workout_repo.create(
                WorkoutCreate(
                    date=date,
                    exercise=item["exercise"],
                    category=item["category"],
                    weight=item.get("weight"),
                    reps=item.get("reps"),
                    distance=item.get("distance"),
                    distance_unit=item.get("distance_unit"),
                    time=item.get("time"),
                    # The cue travels with the set. It is also the field the
                    # user overwrites with feedback afterwards, which is the
                    # whole read-back channel (Plan 0012 §4) - so a prescription
                    # cue is written to be replaced, not preserved.
                    comment=item.get("comment"),
                    order=start_order + offset,
                    is_mobility=True,
                )
            )

        count = self.upcoming_repo.delete_session(session_id, kind=MOBILITY)
        self.mobility_repo.record_session_note(session_id, date)

        return {
            "date": date,
            "count": count,
            "label": plan["label"],
            "message": f"Copied {count} sets from '{plan['label']}' to {date}",
        }

    def log_movement_break(
        self, exercise: str, sets: int, seconds: int, date: str | None = None
    ) -> dict | None:
        """Write one finished movement break run onto a day as mobility sets.

        None when no such movement exists, so the route can 404 rather than
        report a run that wrote nothing.

        One row per work interval, which is the grain the rest of the schema
        works at: `workouts` has no "sets" column, and two 30 second holds are
        two sets.

        `reps` is deliberately NULL and the duration goes in `time`. A timed
        hold is not a rep, and writing `reps = 1` for one would put a rep in the
        progression series that never happened (ADR-0005).

        `seconds` is what the timer was set to when the run ended, not the
        movement's default bout — the times are adjustable after a shuffle, and
        the log records what was done.

        No comment is written. That field is the user's feedback channel and the
        only one there is (0012 §4); a run that finished has nothing to say
        about itself.
        """
        movement = self.exercise_repo.get_by_name(exercise)
        if not movement:
            return None

        day = date or get_current_date()
        now = get_current_datetime()
        # `m:ss` — the format `workouts.time` is written in.
        duration = f"{seconds // 60}:{seconds % 60:02d}"

        existing = self.workout_repo.get_by_date(day)
        start_order = max((w.get("order") or 0) for w in existing) if existing else 0

        ids = []
        for offset in range(1, sets + 1):
            created = self.workout_repo.create(
                WorkoutCreate(
                    date=day,
                    exercise=exercise,
                    category=movement["category"],
                    weight=None,
                    reps=None,
                    time=duration,
                    # Already ticked: it was run, which is the only reason this
                    # row is being written at all.
                    completed_at=now,
                    # Several snacks in one afternoon stack in the order they
                    # were run, never interleaved with what was already there.
                    order=start_order + offset,
                    is_mobility=True,
                )
            )
            ids.append(created["doc_id"])

        return {
            "date": day,
            "exercise": exercise,
            "sets": sets,
            "time": duration,
            "ids": ids,
            "message": (
                f"Logged {sets} x {duration} of {exercise} to {day} as mobility work"
            ),
        }

    def clear_pending(self, session_id: int) -> int:
        """Discard one pending session without running it.

        Both halves go: the rows and the plan row that names them. Leaving the
        plan behind would put an empty heading on the page, and leaving the
        rows behind would orphan them under a session nothing points at.
        """
        removed = self.upcoming_repo.delete_session(session_id, kind=MOBILITY)
        self.mobility_repo.delete_plan(session_id)
        return removed
