"""Wendler 5/3/1 Progression Generator Service.

Generates upcoming workouts based on the Wendler 5/3/1 program,
using the latest logged workout data to determine starting weights.
"""

from typing import Optional
from app.repositories.workout_repo import WorkoutRepository
from app.repositories.upcoming_repo import UpcomingWorkoutRepository
from app.models.upcoming import UpcomingWorkoutCreate
from app.utils.calculations import calculate_estimated_1rm


class WendlerService:
    """Service for generating Wendler 5/3/1 progression workouts."""

    # Main lifts and their categories
    MAIN_LIFTS = {
        "Barbell Squat": "Legs",
        "Flat Barbell Bench Press": "Push",
        "Deadlift": "Pull",
    }

    # Accessory exercises for each day
    ACCESSORIES = {
        "squat_day": [
            ("Pull Up", "Pull", "Bodyweight"),
            ("Incline Dumbbell Press", "Push", None),
            ("Decline Crunch", "Core", None),
        ],
        "bench_day": [
            ("Front Squat", "Legs", None),
            ("Dumbbell Row", "Pull", None),
            ("Landmines", "Core", None),
        ],
        "deadlift_day": [
            ("Parallel Bar Triceps Dip", "Push", "Bodyweight"),
            ("Bulgarian Split Squat", "Legs", None),
            ("Cable side bend", "Core", None),
        ],
    }

    # Wendler percentages by week: (percentage, reps)
    WEEK_PERCENTAGES = {
        1: [(0.65, 5), (0.75, 5), (0.85, 5)],
        2: [(0.70, 3), (0.80, 3), (0.90, 3)],
        3: [(0.75, 5), (0.85, 3), (0.95, 1)],
        4: [(0.40, 5), (0.50, 5), (0.60, 5)],  # Deload
    }

    def __init__(self):
        self.workout_repo = WorkoutRepository()
        self.upcoming_repo = UpcomingWorkoutRepository()

    def get_latest_estimated_1rm(self, exercise: str) -> Optional[float]:
        """
        Get the latest estimated 1RM for an exercise based on historical data.

        Args:
            exercise: Exercise name

        Returns:
            Estimated 1RM value or None if no data
        """
        workouts = self.workout_repo.get_by_exercise(exercise)
        workouts = [w for w in workouts if w.get("weight") and w.get("reps")]

        if not workouts:
            return None

        # Get the most recent workout (list is sorted by date)
        recent_workouts = workouts[-10:]  # Look at last 10 entries

        best_1rm = 0
        for workout in recent_workouts:
            weight = workout.get("weight", 0)
            reps = workout.get("reps", 0)
            estimated = calculate_estimated_1rm(weight, reps)
            if estimated > best_1rm:
                best_1rm = estimated

        return best_1rm if best_1rm > 0 else None

    def calculate_weights(self, max_weight: float, week: int) -> list[tuple[int, int]]:
        """
        Calculate weights for a given 1RM and week in Wendler 5/3/1 program.

        Args:
            max_weight: Current 1RM for the lift
            week: Week number (1-4)

        Returns:
            List of tuples (weight, reps) for each set
        """
        weights = []
        for pct, reps in self.WEEK_PERCENTAGES[week]:
            weight = max_weight * pct
            # Round to nearest 5
            weight = round(weight / 5) * 5
            # If ends in 0, subtract 5 (assumes no 2.5 lb plates available)
            if weight % 10 == 0:
                weight -= 5
            weights.append((int(weight), reps))

        return weights

    def get_current_maxes(self) -> dict[str, float]:
        """
        Get current estimated 1RM for all main lifts.

        Returns:
            Dict mapping exercise name to estimated 1RM
        """
        maxes = {}
        for exercise in self.MAIN_LIFTS.keys():
            estimated = self.get_latest_estimated_1rm(exercise)
            if estimated:
                maxes[exercise] = estimated
        return maxes

    def generate_progression(
        self,
        num_cycles: int = 4,
        squat_max: Optional[float] = None,
        bench_max: Optional[float] = None,
        deadlift_max: Optional[float] = None,
    ) -> list[UpcomingWorkoutCreate]:
        """
        Generate Wendler 5/3/1 progression workouts.

        Args:
            num_cycles: Number of 4-week cycles to generate
            squat_max: Override 1RM for squat (uses latest data if None)
            bench_max: Override 1RM for bench (uses latest data if None)
            deadlift_max: Override 1RM for deadlift (uses latest data if None)

        Returns:
            List of UpcomingWorkoutCreate objects
        """
        # Get current maxes if not provided
        current_maxes = self.get_current_maxes()

        starting_squat = squat_max or current_maxes.get("Barbell Squat", 225)
        starting_bench = bench_max or current_maxes.get("Flat Barbell Bench Press", 185)
        starting_deadlift = deadlift_max or current_maxes.get("Deadlift", 275)

        # Find the next session number
        existing = self.upcoming_repo.get_all()
        if existing:
            max_session = max(w.get("session", 0) for w in existing)
            start_session = max_session + 1
        else:
            start_session = 1

        workouts = []
        session_num = start_session

        for cycle_idx in range(num_cycles):
            # Progressive overload: add 10lbs to squat/deadlift, 5lbs to bench per cycle
            squat_1rm = starting_squat + (cycle_idx * 10)
            bench_1rm = starting_bench + (cycle_idx * 5)
            deadlift_1rm = starting_deadlift + (cycle_idx * 10)

            for week in range(1, 5):
                week_label = f"Week {week}" if week < 4 else "Week 4 Deload"

                # Day 1 - Squat
                squat_weights = self.calculate_weights(squat_1rm, week)
                for set_idx, (weight, reps) in enumerate(squat_weights, 1):
                    workouts.append(
                        UpcomingWorkoutCreate(
                            session=session_num,
                            exercise="Barbell Squat",
                            category="Legs",
                            weight=weight,
                            weight_unit="lbs",
                            reps=reps,
                            comment=f"{week_label} - Set {set_idx}",
                        )
                    )

                # Squat day accessories
                for exercise, category, comment in self.ACCESSORIES["squat_day"]:
                    workouts.append(
                        UpcomingWorkoutCreate(
                            session=session_num,
                            exercise=exercise,
                            category=category,
                            weight=0 if comment == "Bodyweight" else None,
                            weight_unit="lbs",
                            comment=comment,
                        )
                    )
                session_num += 1

                # Day 2 - Bench
                bench_weights = self.calculate_weights(bench_1rm, week)
                for set_idx, (weight, reps) in enumerate(bench_weights, 1):
                    workouts.append(
                        UpcomingWorkoutCreate(
                            session=session_num,
                            exercise="Flat Barbell Bench Press",
                            category="Push",
                            weight=weight,
                            weight_unit="lbs",
                            reps=reps,
                            comment=f"{week_label} - Set {set_idx}",
                        )
                    )

                # Bench day accessories
                for exercise, category, comment in self.ACCESSORIES["bench_day"]:
                    workouts.append(
                        UpcomingWorkoutCreate(
                            session=session_num,
                            exercise=exercise,
                            category=category,
                            comment=comment,
                        )
                    )
                session_num += 1

                # Day 3 - Deadlift
                deadlift_weights = self.calculate_weights(deadlift_1rm, week)
                for set_idx, (weight, reps) in enumerate(deadlift_weights, 1):
                    workouts.append(
                        UpcomingWorkoutCreate(
                            session=session_num,
                            exercise="Deadlift",
                            category="Pull",
                            weight=weight,
                            weight_unit="lbs",
                            reps=reps,
                            comment=f"{week_label} - Set {set_idx}",
                        )
                    )

                # Deadlift day accessories
                for exercise, category, comment in self.ACCESSORIES["deadlift_day"]:
                    workouts.append(
                        UpcomingWorkoutCreate(
                            session=session_num,
                            exercise=exercise,
                            category=category,
                            weight=0 if comment == "Bodyweight" else None,
                            weight_unit="lbs",
                            comment=comment,
                        )
                    )
                session_num += 1

        return workouts

    def generate_and_save(
        self,
        num_cycles: int = 4,
        squat_max: Optional[float] = None,
        bench_max: Optional[float] = None,
        deadlift_max: Optional[float] = None,
    ) -> dict:
        """
        Generate and save Wendler 5/3/1 progression workouts.

        Args:
            num_cycles: Number of 4-week cycles to generate
            squat_max: Override 1RM for squat
            bench_max: Override 1RM for bench
            deadlift_max: Override 1RM for deadlift

        Returns:
            Summary of generated workouts
        """
        workouts = self.generate_progression(
            num_cycles=num_cycles,
            squat_max=squat_max,
            bench_max=bench_max,
            deadlift_max=deadlift_max,
        )

        if not workouts:
            return {
                "success": False,
                "message": "No workouts generated",
                "count": 0,
            }

        # Save to database
        created = self.upcoming_repo.create_bulk(workouts)

        # Get session range
        sessions = set(w.session for w in workouts)
        min_session = min(sessions)
        max_session = max(sessions)

        return {
            "success": True,
            "message": f"Generated {len(created)} workouts across {len(sessions)} sessions",
            "count": len(created),
            "sessions": len(sessions),
            "session_range": [min_session, max_session],
            "cycles": num_cycles,
        }
