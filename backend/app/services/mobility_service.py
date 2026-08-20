"""The mobility loop: read the pending session, and copy it into the calendar.

The loop has four steps and only two of them are code. The agent reads the last
logged session over MCP and writes the next one; this module is the other half
— it shows the user what is pending and moves it onto a date when they run it.
"""

from app.models.workout import WorkoutCreate
from app.repositories.mobility_repo import MobilityRepository
from app.repositories.upcoming_repo import (
    MOBILITY,
    UpcomingWorkoutRepository,
)
from app.repositories.workout_repo import WorkoutRepository


class MobilityService:
    """Orchestrates the three tables a mobility session touches."""

    def __init__(self) -> None:
        self.upcoming_repo = UpcomingWorkoutRepository()
        self.workout_repo = WorkoutRepository()
        self.mobility_repo = MobilityRepository()

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

    def clear_pending(self, session_id: int) -> int:
        """Discard one pending session without running it.

        Both halves go: the rows and the plan row that names them. Leaving the
        plan behind would put an empty heading on the page, and leaving the
        rows behind would orphan them under a session nothing points at.
        """
        removed = self.upcoming_repo.delete_session(session_id, kind=MOBILITY)
        self.mobility_repo.delete_plan(session_id)
        return removed
