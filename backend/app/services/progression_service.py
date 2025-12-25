"""Progression calculation service."""

from datetime import timedelta
from typing import Optional

from app.repositories.workout_repo import WorkoutRepository
from app.repositories.upcoming_repo import UpcomingWorkoutRepository
from app.utils.calculations import calculate_estimated_1rm
from app.utils.date_helpers import get_current_date, PACIFIC_TZ
from datetime import datetime


class ProgressionService:
    """Service for calculating and projecting exercise progression."""

    def __init__(self):
        self.workout_repo = WorkoutRepository()
        self.upcoming_repo = UpcomingWorkoutRepository()

    def get_progression_data(self, exercise: str, include_upcoming: bool = True) -> dict:
        """
        Get progression data for an exercise.

        Args:
            exercise: Exercise name
            include_upcoming: Whether to include upcoming workouts

        Returns:
            Dict with 'historical' and 'upcoming' progression data
        """
        # Get historical workouts
        historical_workouts = self.workout_repo.get_by_exercise(exercise)
        historical_workouts = [
            w for w in historical_workouts
            if w.get('weight') is not None
        ]

        # Group by date and get best set per date
        historical_by_date = {}
        for workout in historical_workouts:
            date = workout.get('date', '')
            weight = workout.get('weight')
            reps = workout.get('reps')

            if not weight or not reps:
                continue

            estimated_1rm = calculate_estimated_1rm(weight, reps)

            if (date not in historical_by_date or
                estimated_1rm > historical_by_date[date]['estimated_1rm']):
                historical_by_date[date] = {
                    'date': date,
                    'weight': weight,
                    'weight_unit': workout.get('weight_unit', 'lbs'),
                    'reps': reps,
                    'estimated_1rm': estimated_1rm,
                    'comment': workout.get('comment'),
                }

        historical = list(historical_by_date.values())
        historical.sort(key=lambda x: x['date'])

        upcoming = []

        if include_upcoming:
            # Get ALL upcoming workouts to build session-to-date mapping
            all_upcoming = self.upcoming_repo.get_all()

            # Group by session
            sessions = {}
            for workout in all_upcoming:
                session = workout.get('session')
                if session not in sessions:
                    sessions[session] = []
                sessions[session].append(workout)

            # Determine start date for projections
            if historical:
                last_date_str = historical[-1]['date']
                try:
                    last_date = datetime.fromisoformat(last_date_str).date()
                    start_date = last_date + timedelta(days=2)
                except (ValueError, TypeError):
                    start_date = datetime.now(PACIFIC_TZ).date()
            else:
                start_date = datetime.now(PACIFIC_TZ).date()

            # Map ALL sessions to dates
            session_to_date = {}
            current_date = start_date
            for session_num in sorted(sessions.keys()):
                session_to_date[session_num] = current_date.isoformat()
                current_date += timedelta(days=2)

            # Filter for the selected exercise and build upcoming list
            for session_num in sorted(sessions.keys()):
                session_workouts = sessions[session_num]

                # Filter for the selected exercise
                exercise_workouts = [
                    w for w in session_workouts
                    if w.get('exercise') == exercise and w.get('weight')
                ]

                if not exercise_workouts:
                    continue

                projected_date = session_to_date[session_num]

                # Find best set for this exercise in this session
                best_workout = None
                best_estimated_1rm = 0

                for workout in exercise_workouts:
                    weight = workout.get('weight')
                    reps = workout.get('reps')

                    if not weight or not reps:
                        continue

                    estimated_1rm = calculate_estimated_1rm(weight, reps)

                    if estimated_1rm > best_estimated_1rm:
                        best_estimated_1rm = estimated_1rm
                        best_workout = {
                            'session': session_num,
                            'projected_date': projected_date,
                            'weight': weight,
                            'weight_unit': workout.get('weight_unit', 'lbs'),
                            'reps': reps,
                            'estimated_1rm': estimated_1rm,
                            'comment': workout.get('comment'),
                        }

                if best_workout:
                    upcoming.append(best_workout)

        return {
            'exercise': exercise,
            'historical': historical,
            'upcoming': upcoming,
        }

    def get_main_lifts_progression(self) -> dict:
        """Get progression data for the main 3 lifts."""
        main_lifts = [
            'Flat Barbell Bench Press',
            'Barbell Squat',
            'Deadlift',
        ]

        result = {}
        for lift in main_lifts:
            result[lift] = self.get_progression_data(lift)

        return result
