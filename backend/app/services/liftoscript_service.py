"""Liftoscript Parser Service.

Parses Liftoscript workout program syntax and generates upcoming workouts.
Supports exercises, sets, reps, weights (absolute and percentage), and comments.
"""

import re
from typing import Optional
from app.models.upcoming import UpcomingWorkoutCreate


class LiftoscriptParser:
    """Parser for Liftoscript workout program syntax."""

    # Category inference rules based on exercise name keywords
    CATEGORY_RULES = {
        "Legs": ["squat", "leg", "lunge", "calf", "split squat", "bulgarian"],
        "Push": [
            "bench",
            "press",
            "dip",
            "push",
            "tricep",
            "shoulder",
            "fly",
            "incline",
            "decline",
        ],
        "Pull": ["deadlift", "row", "pull", "curl", "lat", "back", "chin"],
        "Core": ["crunch", "plank", "cable side", "landmine", "ab", "core", "oblique"],
    }

    # Regex patterns for parsing
    WEEK_HEADER_PATTERN = re.compile(r"^#\s*Week\s*(\d+)", re.IGNORECASE)
    DAY_HEADER_PATTERN = re.compile(r"^##\s*(.+)$")
    COMMENT_PATTERN = re.compile(r"^//\s*(.*)$")
    EXERCISE_PATTERN = re.compile(r"^(.+?)\s*/\s*(.+)$")

    # Set patterns: "3x8", "1x5+", "3x8-12"
    SET_PATTERN = re.compile(r"(\d+)x(\d+)(\+)?(?:-(\d+))?")

    # Weight patterns: "65%", "60lb", "60kg"
    WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)(lb|kg|%)")

    def __init__(self):
        self.session_num = 1
        self.current_comment = None

    def _infer_category(self, exercise_name: str) -> str:
        """Infer the exercise category from its name."""
        exercise_lower = exercise_name.lower()

        for category, keywords in self.CATEGORY_RULES.items():
            for keyword in keywords:
                if keyword in exercise_lower:
                    return category

        return "Other"

    def _get_max_for_exercise(
        self,
        exercise_name: str,
        squat_max: float,
        bench_max: float,
        deadlift_max: float,
    ) -> float:
        """Determine which 1RM to use for an exercise based on its name."""
        exercise_lower = exercise_name.lower()

        if "squat" in exercise_lower:
            return squat_max
        elif "bench" in exercise_lower or "press" in exercise_lower:
            return bench_max
        elif "deadlift" in exercise_lower:
            return deadlift_max

        # Default to bench max for unknown exercises using percentages
        return bench_max

    def _round_weight(self, weight: float) -> int:
        """
        Round weight to nearest 5lb, then subtract 5 if ends in 0.
        This accounts for not having 2.5lb plates available.
        """
        # Round to nearest 5
        rounded = round(weight / 5) * 5
        # If ends in 0, subtract 5
        if rounded % 10 == 0 and rounded > 0:
            rounded -= 5
        return int(rounded)

    def _convert_kg_to_lbs(self, kg: float) -> float:
        """Convert kilograms to pounds."""
        return kg * 2.20462

    def _parse_set_spec(
        self,
        set_spec: str,
        exercise_name: str,
        squat_max: float,
        bench_max: float,
        deadlift_max: float,
    ) -> list[dict]:
        """
        Parse a set specification like "3x8 65%" or "1x5, 1x3, 1x1".

        Returns a list of dicts with keys: sets, reps, weight, weight_unit
        """
        results = []

        # Split by comma for multiple set definitions
        set_parts = [s.strip() for s in set_spec.split(",")]

        for part in set_parts:
            # Extract the set/rep pattern
            set_match = self.SET_PATTERN.search(part)
            if not set_match:
                continue

            num_sets = int(set_match.group(1))
            reps = set_match.group(2)
            is_amrap = set_match.group(3) is not None  # Has "+"
            max_reps = set_match.group(4)  # For rep ranges like "8-12"

            # Format reps string
            if is_amrap:
                reps_str = f"{reps}+"
            elif max_reps:
                reps_str = f"{reps}-{max_reps}"
            else:
                reps_str = reps

            # Extract weight if present
            weight = None
            weight_unit = "lbs"

            weight_match = self.WEIGHT_PATTERN.search(part)
            if weight_match:
                weight_value = float(weight_match.group(1))
                weight_type = weight_match.group(2)

                if weight_type == "%":
                    # Calculate weight from percentage of 1RM
                    max_weight = self._get_max_for_exercise(
                        exercise_name, squat_max, bench_max, deadlift_max
                    )
                    weight = self._round_weight(max_weight * (weight_value / 100))
                    weight_unit = "lbs"
                elif weight_type == "kg":
                    # Convert kg to lbs and round
                    weight = self._round_weight(self._convert_kg_to_lbs(weight_value))
                    weight_unit = "lbs"
                else:  # "lb"
                    weight = self._round_weight(weight_value)
                    weight_unit = "lbs"

            results.append(
                {
                    "num_sets": num_sets,
                    "reps": reps_str,
                    "weight": weight,
                    "weight_unit": weight_unit,
                }
            )

        return results

    def parse(
        self,
        script: str,
        squat_max: float = 225,
        bench_max: float = 185,
        deadlift_max: float = 275,
        num_cycles: int = 1,
    ) -> list[UpcomingWorkoutCreate]:
        """
        Parse a Liftoscript program and generate upcoming workouts.

        Args:
            script: The Liftoscript program text
            squat_max: 1RM for squat exercises
            bench_max: 1RM for bench/press exercises
            deadlift_max: 1RM for deadlift exercises
            num_cycles: Number of times to repeat the program

        Returns:
            List of UpcomingWorkoutCreate objects
        """
        workouts = []
        self.session_num = 1

        for cycle_idx in range(num_cycles):
            # Progressive overload per cycle
            cycle_squat_max = squat_max + (cycle_idx * 10)
            cycle_bench_max = bench_max + (cycle_idx * 5)
            cycle_deadlift_max = deadlift_max + (cycle_idx * 10)

            # Parse the script for this cycle
            cycle_workouts = self._parse_single_cycle(
                script,
                cycle_squat_max,
                cycle_bench_max,
                cycle_deadlift_max,
            )
            workouts.extend(cycle_workouts)

        return workouts

    def _parse_single_cycle(
        self,
        script: str,
        squat_max: float,
        bench_max: float,
        deadlift_max: float,
    ) -> list[UpcomingWorkoutCreate]:
        """Parse a single cycle of the program."""
        workouts = []
        current_comment = None
        in_session = False

        lines = script.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                current_comment = None
                continue

            # Check for week header (informational only)
            if self.WEEK_HEADER_PATTERN.match(line):
                continue

            # Check for day header (starts a new session)
            day_match = self.DAY_HEADER_PATTERN.match(line)
            if day_match:
                # Only increment session if we've already started one
                if in_session:
                    self.session_num += 1
                in_session = True
                current_comment = None
                continue

            # Check for comment (becomes workout comment for next exercise)
            comment_match = self.COMMENT_PATTERN.match(line)
            if comment_match:
                current_comment = comment_match.group(1).strip()
                continue

            # Check for exercise declaration
            exercise_match = self.EXERCISE_PATTERN.match(line)
            if exercise_match and in_session:
                exercise_name = exercise_match.group(1).strip()
                set_spec = exercise_match.group(2).strip()

                category = self._infer_category(exercise_name)

                # Parse the set specification
                set_definitions = self._parse_set_spec(
                    set_spec,
                    exercise_name,
                    squat_max,
                    bench_max,
                    deadlift_max,
                )

                # Create workout entries for each set definition
                first_workout = True
                for set_def in set_definitions:
                    for set_num in range(set_def["num_sets"]):
                        # Only include comment on the very first workout entry
                        comment = current_comment if first_workout else None
                        first_workout = False

                        # Parse reps - handle AMRAP and ranges
                        reps_str = set_def["reps"]
                        reps_value = None

                        # Try to extract numeric reps
                        if reps_str:
                            # For AMRAP (e.g., "5+"), use the base number
                            if reps_str.endswith("+"):
                                try:
                                    reps_value = int(reps_str[:-1])
                                except ValueError:
                                    pass
                            # For ranges (e.g., "8-12"), use the lower bound
                            elif "-" in reps_str:
                                try:
                                    reps_value = int(reps_str.split("-")[0])
                                except ValueError:
                                    pass
                            else:
                                try:
                                    reps_value = int(reps_str)
                                except ValueError:
                                    pass

                        workout = UpcomingWorkoutCreate(
                            session=self.session_num,
                            exercise=exercise_name,
                            category=category,
                            weight=set_def["weight"],
                            weight_unit=set_def["weight_unit"],
                            reps=reps_value,
                            comment=comment,
                        )
                        workouts.append(workout)

                # Clear comment after using it
                current_comment = None

        # Increment session for next cycle
        if in_session:
            self.session_num += 1

        return workouts
