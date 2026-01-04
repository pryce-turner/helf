"""Workout repository for database operations."""

from tinydb import Query
from datetime import datetime
from typing import Optional

from app.database import get_table, WORKOUTS_TABLE
from app.models.workout import WorkoutCreate, WorkoutUpdate
from app.utils.date_helpers import get_current_datetime


class WorkoutRepository:
    """Repository for workout data operations."""

    def __init__(self):
        self.table = get_table(WORKOUTS_TABLE)
        self.query = Query()

    def get_all(self, skip: int = 0, limit: int = 100) -> list[dict]:
        """Get all workouts with pagination."""
        # Get all documents with their doc_ids
        all_workouts = []
        for doc in self.table.all():
            doc_with_id = {**doc, 'doc_id': doc.doc_id}
            all_workouts.append(doc_with_id)

        # Sort by date descending, then by order
        all_workouts.sort(key=lambda x: (x.get('date', ''), x.get('order') or 0), reverse=True)
        return all_workouts[skip:skip+limit]

    def get_by_id(self, doc_id: int) -> Optional[dict]:
        """Get a workout by ID."""
        doc = self.table.get(doc_id=doc_id)
        if doc:
            return {**doc, 'doc_id': doc.doc_id}
        return None

    def get_by_date(self, date: str) -> list[dict]:
        """Get all workouts for a specific date, sorted by order."""
        results = self.table.search(self.query.date == date)
        # Add doc_id to each workout, ensuring order is never None
        workouts = []
        for doc in results:
            workout = {**doc, 'doc_id': doc.doc_id}
            # Ensure order is always a valid integer
            if workout.get('order') is None:
                workout['order'] = 0
            workouts.append(workout)
        workouts.sort(key=lambda x: x['order'])
        return workouts

    def create(self, workout: WorkoutCreate) -> dict:
        """Create a new workout."""
        now = get_current_datetime()
        workout_dict = workout.model_dump(exclude_none=False)
        workout_dict['created_at'] = now.isoformat()
        workout_dict['updated_at'] = now.isoformat()

        # Auto-assign order if not provided
        if workout_dict.get('order') is None:
            date_workouts = self.get_by_date(workout.date)
            workout_dict['order'] = len(date_workouts) + 1

        doc_id = self.table.insert(workout_dict)
        doc = self.table.get(doc_id=doc_id)
        return {**doc, 'doc_id': doc.doc_id}

    def update(self, doc_id: int, workout: WorkoutUpdate) -> Optional[dict]:
        """Update an existing workout."""
        if not self.table.get(doc_id=doc_id):
            return None

        workout_dict = workout.model_dump(exclude_none=False)
        workout_dict['updated_at'] = get_current_datetime().isoformat()

        self.table.update(workout_dict, doc_ids=[doc_id])
        doc = self.table.get(doc_id=doc_id)
        return {**doc, 'doc_id': doc.doc_id}

    def delete(self, doc_id: int) -> bool:
        """Delete a workout."""
        removed = self.table.remove(doc_ids=[doc_id])
        return len(removed) > 0

    def toggle_complete(self, doc_id: int, completed: bool) -> Optional[dict]:
        """Mark a workout as complete or incomplete."""
        if not self.table.get(doc_id=doc_id):
            return None

        now = get_current_datetime()
        update_data = {
            'completed_at': now.isoformat() if completed else None,
            'updated_at': now.isoformat()
        }

        self.table.update(update_data, doc_ids=[doc_id])
        doc = self.table.get(doc_id=doc_id)
        return {**doc, 'doc_id': doc.doc_id}

    def reorder(self, doc_id: int, date: str, direction: str) -> bool:
        """
        Reorder a workout within its date.

        Args:
            doc_id: ID of the workout to reorder
            date: Date of the workout
            direction: 'up' or 'down'

        Returns:
            True if successful, False otherwise
        """
        date_workouts = self.get_by_date(date)

        # Find the workout index
        workout_index = None
        for i, w in enumerate(date_workouts):
            if w['doc_id'] == doc_id:
                workout_index = i
                break

        if workout_index is None:
            return False

        # Check boundaries
        if direction == 'up' and workout_index == 0:
            return False
        if direction == 'down' and workout_index == len(date_workouts) - 1:
            return False

        # Swap with adjacent workout
        if direction == 'up':
            swap_index = workout_index - 1
        else:
            swap_index = workout_index + 1

        # Update order values
        date_workouts[workout_index]['order'] = swap_index + 1
        date_workouts[swap_index]['order'] = workout_index + 1

        # Save updates
        self.table.update(
            {'order': date_workouts[workout_index]['order']},
            doc_ids=[date_workouts[workout_index]['doc_id']]
        )
        self.table.update(
            {'order': date_workouts[swap_index]['order']},
            doc_ids=[date_workouts[swap_index]['doc_id']]
        )

        return True

    def get_workout_counts_by_date(self, year: int, month: int) -> dict[str, int]:
        """Get workout counts grouped by date for a specific month."""
        # Search for all workouts in the month
        pattern = f'{year}-{month:02d}'
        workouts = self.table.search(self.query.date.matches(f'^{pattern}-.*'))

        counts = {}
        for workout in workouts:
            date = workout['date']
            counts[date] = counts.get(date, 0) + 1

        return counts

    def get_by_exercise(self, exercise: str) -> list[dict]:
        """Get all workouts for a specific exercise."""
        workouts = self.table.search(self.query.exercise == exercise)
        workouts.sort(key=lambda x: x.get('date', ''))
        return workouts
