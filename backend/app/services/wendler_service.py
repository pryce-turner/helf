"""Wendler Service - 1RM Detection.

Provides estimated 1RM values based on workout history.
Used to populate default values for Liftoscript programs that use percentage notation.
"""


from app.repositories.workout_repo import WorkoutRepository
from app.utils.calculations import calculate_estimated_1rm


class WendlerService:
    """Service for detecting current 1RM values from workout history."""

    # Main lifts for 1RM detection
    MAIN_LIFTS = {
        "Barbell Squat": "Legs",
        "Flat Barbell Bench Press": "Push",
        "Deadlift": "Pull",
    }

    def __init__(self):
        self.workout_repo = WorkoutRepository()

    def get_latest_estimated_1rm(self, exercise: str) -> float | None:
        """Get the latest estimated 1RM for an exercise based on historical data.

        Args:
            exercise: Exercise name

        Returns:
            Estimated 1RM value or None if no data
        """
        workouts = self.workout_repo.get_by_exercise(exercise)
        workouts = [w for w in workouts if w.get("weight") and w.get("reps")]

        if not workouts:
            return None

        # Get the most recent workouts and find best 1RM
        recent_workouts = workouts[-10:]

        best_1rm = 0
        for workout in recent_workouts:
            weight = workout.get("weight", 0)
            reps = workout.get("reps", 0)
            estimated = calculate_estimated_1rm(weight, reps)
            if estimated > best_1rm:
                best_1rm = estimated

        return best_1rm if best_1rm > 0 else None

    def get_current_maxes(self) -> dict[str, float]:
        """Get current estimated 1RM for all main lifts.

        Returns:
            Dict mapping exercise name to estimated 1RM
        """
        maxes = {}
        for exercise in self.MAIN_LIFTS.keys():
            estimated = self.get_latest_estimated_1rm(exercise)
            if estimated:
                maxes[exercise] = estimated
        return maxes
