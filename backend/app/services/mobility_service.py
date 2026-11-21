"""The mobility loop's service half: the shuffle, the write, the read-back.

The loop has four steps and only two of them are code. The agent reads the last
logged session over MCP and writes the next one; this module shows the user
what came of it and inserts movement-break suggestions. The pending queue
itself is just the upcoming queue now (9c4e7b21f806) — listing, transferring
and discarding sessions lives on the upcoming routes, and what remains here is
what is genuinely mobility's: the movement-break shuffle and the agent's
write path.
"""

import random

from app.models.workout import WorkoutCreate
from app.repositories.exercise_repo import ExerciseRepository
from app.repositories.mobility_repo import MobilityRepository
from app.repositories.workout_repo import WorkoutRepository
from app.utils.date_helpers import get_current_date

#: How many candidates the shuffle draws before picking one. Three and a
#: least-recently-used tiebreak, not a uniform draw: uniform hands back the
#: movement just done one time in twenty-eight, which for something run
#: several times a day is a repeat most days.
SHUFFLE_CANDIDATES = 3


def _shuffle(pool: list[dict]) -> dict:
    """Three candidates at random, then the least recently used of them.

    `last_used` reads performed work only (plan 0018) — a suggested tile that
    was never played cannot make its movement look done. NULLs sort first:
    never done is the most overdue.
    """
    drawn = random.sample(pool, k=min(SHUFFLE_CANDIDATES, len(pool)))
    return min(drawn, key=lambda movement: movement["last_used"] or "")


class MobilityService:
    """The movement-break shuffle, and the agent's session write."""

    def __init__(self) -> None:
        self.workout_repo = WorkoutRepository()
        self.mobility_repo = MobilityRepository()
        self.exercise_repo = ExerciseRepository()

    def get_last_session(self) -> dict | None:
        """The last mobility session that reached the calendar, with its sets.

        Read back on the upcoming page, where the comments it carries are what
        the next prescription gets written from.
        """
        return self.mobility_repo.get_latest_logged()

    def write_pending(self, label: str, rationale: str, items: list[dict]) -> dict:
        """Write one pending session under `label`. See `MobilityRepository.write_session`."""
        return self.mobility_repo.write_session(label, rationale, items)

    def suggest_movement_break(self, date: str | None = None) -> dict | None:
        """Insert a suggested, incomplete mobility tile on a day.

        Replaces the old finished-run writer (plan 0018): the suggestion is an
        ordinary planned tile holding the movement's defaults — the shuffle's
        pick, the exercise's field defaults, `is_mobility` set — which the day
        player then performs like anything else. It counts as nothing until
        played: `last_used` and the calendar move at performance, so a
        suggestion the user ignores costs nothing.

        Appended at the day's end rather than below the last completed set —
        the suggestion is for *later*, and slotting it above the day's planned
        work would push it into the middle of a session.

        None when the pool is empty, so the route can 404 rather than report a
        suggestion that does not exist.
        """
        pool = self.exercise_repo.get_movement_breaks()
        if not pool:
            return None

        movement = _shuffle(pool)
        day = date or get_current_date()

        existing = self.workout_repo.get_by_date(day)
        start_order = max((w.get("order") or 0) for w in existing) if existing else 0

        return self.workout_repo.create(
            WorkoutCreate(
                date=day,
                exercise=movement["name"],
                category=movement["category"],
                weight=movement["default_weight_lb"],
                reps=movement["default_reps"],
                distance=movement["default_distance"],
                distance_unit=movement["default_distance_unit"],
                work_seconds=movement["default_work_seconds"],
                rest_seconds=movement["default_rest_seconds"],
                rest_after_seconds=movement["default_rest_after_seconds"],
                order=start_order + 1,
                is_mobility=True,
            )
        )
