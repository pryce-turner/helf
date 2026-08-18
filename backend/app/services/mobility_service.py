"""The mobility loop: read the pending session, and copy it into the calendar.

The loop has four steps and only two of them are code. The agent reads the last
logged session over MCP and writes the next one; this module is the other half
— it shows the user what is pending and moves it onto a date when they run it.
"""

from app.models.workout import WorkoutCreate
from app.repositories.mobility_repo import MobilityRepository
from app.repositories.upcoming_repo import (
    MOBILITY,
    MOBILITY_SESSION,
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
        """The pending session and the last one that was run.

        Both states of the page come out of this one call. `ready` is derived
        from whether any items exist rather than stored, so there is no status
        column that can disagree with the rows it describes.
        """
        items = self.upcoming_repo.get_by_session(MOBILITY_SESSION, kind=MOBILITY)
        plan_note = self.mobility_repo.get_plan_note()

        return {
            "ready": bool(items),
            "items": items,
            # A rationale with no items is a leftover, not a plan. Reporting it
            # would explain a session the user cannot see.
            "rationale": plan_note["body"] if plan_note and items else None,
            "generated_at": plan_note["noted_at"] if plan_note and items else None,
            "last_session": self.mobility_repo.get_latest_logged(),
        }

    def transfer(self, date: str) -> dict:
        """Copy the pending session onto `date`, and mark that day as mobility.

        The order matters. Workout rows are appended **after** anything already
        logged that day, because a mobility session run alongside lifting is
        still one day's work and the existing `order` values are what put it in
        sequence.

        The note is promoted last. Until it is, the day is not a mobility day
        as far as the read path is concerned, so a failure part-way through
        leaves sets that look like ordinary training rather than a session the
        agent will read back as complete.
        """
        items = self.upcoming_repo.get_by_session(MOBILITY_SESSION, kind=MOBILITY)
        if not items:
            return {"date": date, "count": 0, "message": "No pending mobility session"}

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
                    # whole read-back channel (Plan 0012 §4) — so a prescription
                    # cue is written to be replaced, not preserved.
                    comment=item.get("comment"),
                    order=start_order + offset,
                )
            )

        count = self.upcoming_repo.delete_session(MOBILITY_SESSION, kind=MOBILITY)
        self.mobility_repo.promote_plan_note(date)

        return {
            "date": date,
            "count": count,
            "message": f"Copied {count} mobility sets to {date}",
        }

    def clear_pending(self) -> int:
        """Discard the pending session without running it."""
        return self.upcoming_repo.delete_session(MOBILITY_SESSION, kind=MOBILITY)

    def get_day(self, date: str) -> dict:
        """Whether one day is marked as a mobility day, and why if it is."""
        note = self.mobility_repo.get_session_note(date)
        return {
            "date": date,
            "is_mobility": note is not None,
            # Empty means the day was marked by hand rather than transferred,
            # which is a different fact from "no rationale was recorded" only
            # in principle: either way nothing was prescribed for it.
            "rationale": (note["body"] or None) if note else None,
        }

    def set_day(self, date: str, is_mobility: bool) -> dict:
        """Mark or unmark `date` as a mobility day.

        The second way a day acquires the marker that `transfer` writes. It
        exists because the agent reads the *last marked day* to write the next
        session from, and a session run without going through the planner -
        built by hand, or run before the loop existed - is otherwise invisible
        to it while still being the most recent thing that happened.

        Idempotent in both directions so the checkbox can be tapped twice
        without the second tap meaning something different from the first.
        """
        if is_mobility:
            self.mobility_repo.mark_session(date)
        else:
            self.mobility_repo.unmark_session(date)

        return self.get_day(date)
