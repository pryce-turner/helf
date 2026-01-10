"""Liftoscript Parser Service.

Parses Liftoscript workout program syntax and generates upcoming workouts.
Supports exercises, sets, reps, weights (absolute and percentage-based).
"""

import re

from app.models.upcoming import UpcomingWorkoutCreate
from app.repositories.exercise_repo import ExerciseRepository


class LiftoscriptParseError(Exception):
    """Error raised when script parsing fails."""

    pass


class LiftoscriptParser:
    """Parser for Liftoscript workout program syntax.

    Simplified syntax:
    - Exercise lines: "Exercise Name / 3x8 135lb" or "Exercise Name / 1x5 65%"
    - Blank lines separate sessions
    - AMRAP notation: "3x5+" means last set to failure
    - Rep ranges: "3x8-12"
    - Multiple set definitions: "1x5, 1x3, 1x1"
    - Percentage weights: "65%" (requires 1RM input)
    - Absolute weights: "60lb" or "60kg"
    - RPE notation: "@8" stored as metadata
    - Rest time: "20s" stored as metadata
    """

    # Regex patterns for parsing
    # Exercise: "Exercise Name" or "Exercise Name, Equipment"
    EXERCISE_NAME_PATTERN = re.compile(r"^([^,]+?)(?:,\s*(.+?))?$")
    # Set patterns: "3x8", "1x5+", "3+x5" (quick add), "3x8-12"
    SET_PATTERN = re.compile(r"(\d+)(\+)?x(\d+)(\+)?(?:-(\d+))?")

    # Set patterns: "3x8", "1x5+", "3+x5" (quick add), "3x8-12"
    SET_PATTERN = re.compile(r"(\d+)(\+)?x(\d+)(\+)?(?:-(\d+))?")

    # Weight patterns: "65%", "60lb", "60kg", "65%+" (logging indicator)
    WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)(lb|kg|%)(\+)?")

    # RPE pattern: "@8" or "@8.5" or "@8+" (with logging indicator)
    RPE_PATTERN = re.compile(r"@(\d+(?:\.\d+)?)(\+)?")

    # Rest pattern: "20s" or "2m" or "90s"
    REST_PATTERN = re.compile(r"(\d+)(s|m)")

    def __init__(self):
        self.session_num = 1
        self.exercise_repo = ExerciseRepository()

    def _convert_kg_to_lbs(self, kg: float) -> float:
        """Convert kilograms to pounds."""
        return kg * 2.20462

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

    def _validate_exercises(self, script: str) -> dict[str, str]:
        """Validate that all exercises in the script exist in the database.

        Returns:
            Dict mapping exercise name to category.

        Raises:
            LiftoscriptParseError: If any exercises are not found.
        """
        exercise_names = set()

        for line in script.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue

            if "/" in line:
                name_match = self.EXERCISE_NAME_PATTERN.match(line.split("/")[0])
                if name_match:
                    exercise_name = name_match.group(1).strip()
                    exercise_names.add(exercise_name)

        # Look up all exercises
        exercise_categories = {}
        unknown_exercises = []

        for name in exercise_names:
            exercise = self.exercise_repo.get_by_name(name)
            if exercise:
                exercise_categories[name] = exercise["category"]
            else:
                unknown_exercises.append(name)

        if unknown_exercises:
            raise LiftoscriptParseError(
                f"Unknown exercises (not in database): {', '.join(sorted(unknown_exercises))}"
            )

        return exercise_categories

    def _parse_set_spec(
        self,
        set_spec: str,
        exercise_name: str,
        squat_max: float,
        bench_max: float,
        deadlift_max: float,
        global_modifiers: list[str] | None = None,
    ) -> list[dict]:
        """Parse a set specification like "3x8 65%" or "1x5, 1x3, 1x1".

        Returns a list of dicts with keys: num_sets, reps, weight, weight_unit, rpe, rest, is_quick_add, is_log_weight
        """
        results = []
        global_modifiers = global_modifiers or []

        # Parse global modifiers for rest, weight, RPE
        global_rest = None
        global_weight = None
        global_weight_unit = "lbs"
        global_weight_logging = False

        for mod in global_modifiers:
            rest_match = self.REST_PATTERN.search(mod)
            if rest_match and not global_rest:
                rest_value = int(rest_match.group(1))
                rest_unit = rest_match.group(2)
                global_rest = f"{rest_value}{rest_unit}"
                continue

            weight_match = self.WEIGHT_PATTERN.search(mod)
            if weight_match and not global_weight:
                weight_value = float(weight_match.group(1))
                weight_type = weight_match.group(2)
                global_weight_logging = weight_match.group(3) is not None

                if weight_type == "%":
                    max_weight = self._get_max_for_exercise(
                        exercise_name, squat_max, bench_max, deadlift_max
                    )
                    global_weight = round(max_weight * (weight_value / 100))
                elif weight_type == "kg":
                    global_weight = round(self._convert_kg_to_lbs(weight_value))
                else:
                    global_weight = round(weight_value)
                global_weight_unit = "lbs"
                continue

        # Extract RPE if present (applies to all sets in this spec)
        rpe_match = self.RPE_PATTERN.search(set_spec)
        rpe = None
        if rpe_match:
            rpe_value = rpe_match.group(1)
            if rpe_match.group(2):  # Has logging indicator (+)
                rpe = f"{rpe_value}+"  # Store as string with + indicator
            else:
                rpe = float(rpe_value)

        # Extract rest time if present (use global if no inline rest)
        rest_match = self.REST_PATTERN.search(set_spec)
        rest = global_rest
        if rest_match:
            rest_value = int(rest_match.group(1))
            rest_unit = rest_match.group(2)
            rest = f"{rest_value}{rest_unit}"

        # Split by comma for multiple set definitions
        set_parts = [s.strip() for s in set_spec.split(",")]

        for part in set_parts:
            set_match = self.SET_PATTERN.search(part)
            if not set_match:
                continue

            num_sets = int(set_match.group(1))
            is_quick_add = set_match.group(2) is not None
            reps = set_match.group(3)
            is_amrap = set_match.group(4) is not None
            max_reps = set_match.group(5)

            # Format reps string
            if is_amrap:
                reps_str = f"{reps}+"
            elif max_reps:
                reps_str = f"{reps}-{max_reps}"
            else:
                reps_str = reps

            # Extract weight if present (use global if no inline weight)
            weight = global_weight
            weight_unit = global_weight_unit
            is_log_weight = global_weight_logging

            weight_match = self.WEIGHT_PATTERN.search(part)
            if weight_match:
                weight_value = float(weight_match.group(1))
                weight_type = weight_match.group(2)
                is_log_weight = weight_match.group(3) is not None

                if weight_type == "%":
                    # Calculate weight from percentage of 1RM
                    max_weight = self._get_max_for_exercise(
                        exercise_name, squat_max, bench_max, deadlift_max
                    )
                    weight = round(max_weight * (weight_value / 100))
                    weight_unit = "lbs"
                elif weight_type == "kg":
                    # Convert kg to lbs
                    weight = round(self._convert_kg_to_lbs(weight_value))
                    weight_unit = "lbs"
                else:  # "lb"
                    weight = round(weight_value)
                    weight_unit = "lbs"

            results.append(
                {
                    "num_sets": num_sets,
                    "reps": reps_str,
                    "weight": weight,
                    "weight_unit": weight_unit,
                    "rpe": rpe,
                    "rest": rest,
                    "is_quick_add": is_quick_add,
                    "is_log_weight": is_log_weight,
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
        """Parse a Liftoscript program and generate upcoming workouts.

        Args:
            script: The Liftoscript program text
            squat_max: 1RM for squat exercises
            bench_max: 1RM for bench/press exercises
            deadlift_max: 1RM for deadlift exercises
            num_cycles: Number of times to repeat the program

        Returns:
            List of UpcomingWorkoutCreate objects

        Raises:
            LiftoscriptParseError: If exercises are not found in database
        """
        # Validate all exercises exist in database
        exercise_categories = self._validate_exercises(script)

        workouts = []
        self.session_num = 1

        for _ in range(num_cycles):
            cycle_workouts = self._parse_single_cycle(
                script,
                squat_max,
                bench_max,
                deadlift_max,
                exercise_categories,
            )
            workouts.extend(cycle_workouts)

        return workouts

    def _parse_single_cycle(
        self,
        script: str,
        squat_max: float,
        bench_max: float,
        deadlift_max: float,
        exercise_categories: dict[str, str],
    ) -> list[UpcomingWorkoutCreate]:
        """Parse a single cycle of the program."""
        workouts = []
        in_session = False

        lines = script.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Blank line = new session boundary
            if not line or line.startswith("#") or line.startswith("//"):
                if not line and in_session:
                    self.session_num += 1
                    in_session = False
                continue

            # Check for exercise declaration
            if "/" in line:
                in_session = True
                parts = [p.strip() for p in line.split("/")]

                # First part is exercise name with optional equipment
                name_match = self.EXERCISE_NAME_PATTERN.match(parts[0])
                if not name_match:
                    continue

                exercise_name = name_match.group(1).strip()
                equipment = name_match.group(2).strip() if name_match.group(2) else None

                # Remaining parts are set spec and global modifiers
                # First non-empty part that looks like sets is the set spec
                set_spec = None
                global_modifiers = []

                for part in parts[1:]:
                    if not part:
                        continue
                    if set_spec is None and self.SET_PATTERN.search(part):
                        set_spec = part
                    else:
                        global_modifiers.append(part)

                if not set_spec:
                    set_spec = ""

                # Look up category from validated exercises
                category = exercise_categories.get(exercise_name, "Other")

                # Parse the set specification with global modifiers
                set_definitions = self._parse_set_spec(
                    set_spec,
                    exercise_name,
                    squat_max,
                    bench_max,
                    deadlift_max,
                    global_modifiers,
                )

                # Create workout entries for each set definition
                for set_def in set_definitions:
                    for _ in range(set_def["num_sets"]):
                        # Parse reps - handle AMRAP and ranges
                        reps_str = set_def["reps"]
                        reps_value = None
                        is_amrap = False

                        if reps_str:
                            if reps_str.endswith("+"):
                                is_amrap = True
                                try:
                                    reps_value = int(reps_str[:-1])
                                except ValueError:
                                    pass
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

                        # Build comment from RPE, rest, AMRAP, equipment, quick add, log weight if present
                        comment_parts = []
                        if is_amrap:
                            comment_parts.append("AMRAP")
                        if equipment:
                            comment_parts.append(f"Equipment: {equipment}")
                        if set_def.get("is_quick_add"):
                            comment_parts.append("Quick add sets")
                        if set_def.get("is_log_weight"):
                            comment_parts.append("Log weight")
                        if set_def.get("rpe"):
                            rpe_str = str(set_def["rpe"])
                            if rpe_str.endswith("+"):
                                comment_parts.append(f"Log RPE {rpe_str[:-1]}")
                            else:
                                comment_parts.append(f"RPE {rpe_str}")
                        if set_def.get("rest"):
                            comment_parts.append(f"Rest {set_def['rest']}")
                        comment = ", ".join(comment_parts) if comment_parts else None

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

        # Increment session for next cycle if we ended in a session
        if in_session:
            self.session_num += 1

        return workouts
