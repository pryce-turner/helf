"""Upcoming workout repository for database operations."""

from tinydb import Query
from typing import Optional

from app.database import get_table, UPCOMING_TABLE
from app.models.upcoming import UpcomingWorkoutCreate
from app.utils.date_helpers import get_current_datetime


class UpcomingWorkoutRepository:
    """Repository for upcoming workout data operations."""

    def __init__(self):
        self.table = get_table(UPCOMING_TABLE)
        self.query = Query()

    def get_all(self) -> list[dict]:
        """Get all upcoming workouts, sorted by session."""
        workouts = self.table.all()
        workouts = [{**doc, 'doc_id': doc.doc_id} for doc in workouts]
        workouts.sort(key=lambda x: x.get('session', 0))
        return workouts

    def get_by_session(self, session: int) -> list[dict]:
        """Get all workouts for a specific session."""
        workouts = self.table.search(self.query.session == session)
        return [{**doc, 'doc_id': doc.doc_id} for doc in workouts]

    def get_lowest_session(self) -> Optional[int]:
        """Get the lowest session number."""
        workouts = self.table.all()
        if not workouts:
            return None

        # No need to add doc_id since we're only extracting session numbers
        sessions = [w.get('session', 0) for w in workouts if w.get('session')]
        return min(sessions) if sessions else None

    def create(self, workout: UpcomingWorkoutCreate) -> dict:
        """Create a new upcoming workout."""
        now = get_current_datetime()
        workout_dict = workout.model_dump(exclude_none=False)
        workout_dict['created_at'] = now.isoformat()

        doc_id = self.table.insert(workout_dict)
        return self.table.get(doc_id=doc_id)

    def create_bulk(self, workouts: list[UpcomingWorkoutCreate]) -> list[dict]:
        """Create multiple upcoming workouts."""
        now = get_current_datetime()
        created = []

        for workout in workouts:
            workout_dict = workout.model_dump(exclude_none=False)
            workout_dict['created_at'] = now.isoformat()
            doc_id = self.table.insert(workout_dict)
            created.append(self.table.get(doc_id=doc_id))

        return created

    def delete_session(self, session: int) -> int:
        """Delete all workouts in a session. Returns count of deleted workouts."""
        removed = self.table.remove(self.query.session == session)
        return len(removed)

    def get_by_exercise(self, exercise: str) -> list[dict]:
        """Get all upcoming workouts for a specific exercise."""
        workouts = self.table.search(self.query.exercise == exercise)
        workouts = [{**doc, 'doc_id': doc.doc_id} for doc in workouts]
        workouts.sort(key=lambda x: x.get('session', 0))
        return workouts
