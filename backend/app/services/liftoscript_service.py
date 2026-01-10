"""Simplified Liftoscript Parser Service.

Supports: exercise name, sets, reps, 1RM percentage, simple weight, ## Day headers,
comments via //, and linear progression via progress: lp(Xlb). AMRAP indicated by +
converted to comment.

Required comments for percentage/progression:
- If using % for weight: must have "// ExerciseName 1RM: Xlb" at top
- If using progress: lp(): must have "// ExerciseName SW: Xlb" at top (SW = Starting Weight)
"""

import re

from app.models.upcoming import UpcomingWorkoutCreate

# Exercise to category mapping (matches PRESET_EXERCISES in api/exercises.py)
EXERCISE_CATEGORIES = {
    "Barbell Squat": "Legs",
    "Front Squat": "Legs",
    "Bulgarian Split Squat": "Legs",
    "Flat Barbell Bench Press": "Chest",
    "Incline Dumbbell Press": "Chest",
    "Deadlift": "Back",
    "Pull Ups": "Back",
    "Dumbbell Row": "Back",
    "Barbell Row": "Back",
    "Barbell Curl": "Biceps",
    "Dumbbell Curl": "Biceps",
    "Overhead Press": "Triceps",
    "Parallel Bar Triceps Dip": "Triceps",
    "Decline Crunch": "Core",
    "Landmines": "Core",
    "Cable side bend": "Core",
}


class LiftoscriptParseError(Exception):
    """Error raised when script parsing fails."""

    pass


class LiftoscriptParser:
    """Parser for simplified Liftoscript workout program syntax.

    Syntax:
        ## Day Name
        Exercise Name / sets x reps weight
        // Comment

    Weight formats:
        - Percentage: "65%" (requires // ExerciseName 1RM: Xlb comment)
        - Absolute: "135lb" or "60kg"
        - Linear progression: "progress: lp(5lb)" (requires // ExerciseName SW: Xlb comment)

    Examples:
        ## Day 1
        Barbell Squat / 5x5 135lb
        Bench Press / 3x8 80%
        Deadlift / 1x5 65%, 1x3 80%, 1x1+ 95%

        // Squat 1RM: 225lb
        // Bench Press 1RM: 135lb
        // Deadlift 1RM: 315lb
    """

    EXERCISE_NAME_PATTERN = re.compile(r"^([^/]+?)$")
    SET_PATTERN = re.compile(r"(\d+)x(\d+)\+?")
    WEIGHT_PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)%")
    WEIGHT_ABSOLUTE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(lb|kg)")
    PROGRESS_LP_PATTERN = re.compile(r"progress:\s*lp\((\d+(?:\.\d+)?)\s*(lb|kg)\)")
    RPE_PATTERN = re.compile(r"@(\d+(?:\.\d+)?)")
    REST_PATTERN = re.compile(r"(\d+)(s|m)")
    DAY_HEADER_PATTERN = re.compile(r"^##\s+(.+)$")
    REQUIRED_1RM_PATTERN = re.compile(r"^//\s+(.+?)\s+1RM:\s*(\d+(?:\.\d+)?)\s*(lb|kg)$")
    REQUIRED_SW_PATTERN = re.compile(r"^//\s+(.+?)\s+SW:\s*(\d+(?:\.\d+)?)\s*(lb|kg)$")

    def __init__(self):
        self.required_1rms: dict[str, float] = {}
        self.required_sw: dict[str, float] = {}

    def _convert_kg_to_lbs(self, kg: float) -> float:
        return kg * 2.20462

    def _round_to_nearest_5(self, weight: float) -> float:
        """Round weight to nearest 5lb for easier barbell loading."""
        return round(weight / 5) * 5

    def _parse_required_comments(self, script: str) -> None:
        """Parse required 1RM and SW comments from top of script."""
        self.required_1rms = {}
        self.required_sw = {}

        for line in script.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if not line.startswith("//"):
                break

            rm_match = self.REQUIRED_1RM_PATTERN.match(line)
            if rm_match:
                name = rm_match.group(1).strip()
                value = float(rm_match.group(2))
                unit = rm_match.group(3)
                if unit == "kg":
                    value = self._convert_kg_to_lbs(value)
                self.required_1rms[name] = value
                continue

            sw_match = self.REQUIRED_SW_PATTERN.match(line)
            if sw_match:
                name = sw_match.group(1).strip()
                value = float(sw_match.group(2))
                unit = sw_match.group(3)
                if unit == "kg":
                    value = self._convert_kg_to_lbs(value)
                self.required_sw[name] = value

    def _validate_required_comments(
        self, exercise_name: str, uses_percent: bool, uses_progress: bool
    ) -> None:
        """Validate that required comments exist for % and progress exercises."""
        errors = []

        if uses_percent and exercise_name not in self.required_1rms:
            errors.append(
                f"'{exercise_name}' uses % for weight but is missing required comment. "
                f"Add '// {exercise_name} 1RM: Xlb' at the top of the script."
            )

        if uses_progress and exercise_name not in self.required_sw:
            errors.append(
                f"'{exercise_name}' uses progress: lp() but is missing required comment. "
                f"Add '// {exercise_name} SW: Xlb' at the top of the script."
            )

        if errors:
            raise LiftoscriptParseError("; ".join(errors))

    def _parse_weight(
        self,
        weight_str: str,
        exercise_name: str,
        cycle_num: int,
    ) -> tuple[float | None, str]:
        """Parse weight string and return (weight_lbs, unit)."""
        weight_str = weight_str.strip()

        percent_match = self.WEIGHT_PERCENT_PATTERN.search(weight_str)
        if percent_match:
            percent = float(percent_match.group(1))
            if exercise_name not in self.required_1rms:
                self._validate_required_comments(exercise_name, True, False)
            base_max = self.required_1rms.get(exercise_name, 0)
            weight = base_max * (percent / 100)
            return self._round_to_nearest_5(weight), "lbs"

        progress_match = self.PROGRESS_LP_PATTERN.search(weight_str)
        if progress_match:
            increment = float(progress_match.group(1))
            unit = progress_match.group(2)
            if unit == "kg":
                increment = self._convert_kg_to_lbs(increment)
            if exercise_name not in self.required_sw:
                self._validate_required_comments(exercise_name, False, True)
            base_weight = self.required_sw.get(exercise_name, 0)
            total_increment = increment * cycle_num
            weight = base_weight + total_increment
            return self._round_to_nearest_5(weight), "lbs"

        absolute_match = self.WEIGHT_ABSOLUTE_PATTERN.search(weight_str)
        if absolute_match:
            value = float(absolute_match.group(1))
            unit = absolute_match.group(2)
            if unit == "kg":
                value = self._convert_kg_to_lbs(value)
            return round(value), "lbs"

        return None, "lbs"

    def _parse_sets_reps(self, sets_reps_str: str) -> tuple[int, int, bool]:
        """Parse sets and reps string. Returns (sets, reps, is_amrap)."""
        match = self.SET_PATTERN.match(sets_reps_str.strip())
        if not match:
            raise LiftoscriptParseError(f"Invalid sets/reps format: {sets_reps_str}")
        sets = int(match.group(1))
        reps = int(match.group(2))
        is_amrap = "+" in sets_reps_str
        return sets, reps, is_amrap

    def _parse_script(
        self, lines: list[str], cycle_num: int, session_offset: int
    ) -> tuple[list[UpcomingWorkoutCreate], int]:
        """Parse the full script and return workouts."""
        workouts = []
        current_session = 0

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if not line:
                i += 1
                continue

            if line.startswith("//"):
                i += 1
                continue

            day_match = self.DAY_HEADER_PATTERN.match(line)
            if day_match:
                current_session += 1
                i += 1
                continue

            if "/" not in line:
                i += 1
                continue

            parts = [p.strip() for p in line.split("/")]
            exercise_name = parts[0].strip()

            full_spec = parts[1].strip() if len(parts) > 1 else ""

            if not full_spec:
                i += 1
                continue

            # Determine category from exercise name, default to "Other"
            category = EXERCISE_CATEGORIES.get(exercise_name, "Other")

            # Split by comma to handle multiple set specifications (e.g., "1x5 65%, 1x5 75%, 1x5+ 85%")
            set_specs = [spec.strip() for spec in full_spec.split(",")]

            for set_spec in set_specs:
                if not set_spec:
                    continue

                sets, reps, is_amrap = self._parse_sets_reps(set_spec)
                weight, unit = self._parse_weight(set_spec, exercise_name, cycle_num)

                comment_parts = []
                if is_amrap:
                    comment_parts.append("AMRAP")

                comment = ", ".join(comment_parts) if comment_parts else None

                for _ in range(sets):
                    workout = UpcomingWorkoutCreate(
                        session=session_offset + current_session,
                        exercise=exercise_name,
                        category=category,
                        weight=weight,
                        weight_unit=unit,
                        reps=reps,
                        comment=comment,
                    )
                    workouts.append(workout)

            i += 1

        return workouts, current_session

    def parse(
        self,
        script: str,
        num_cycles: int = 1,
    ) -> list[UpcomingWorkoutCreate]:
        """Parse a Liftoscript program and generate upcoming workouts.

        Args:
            script: The Liftoscript program text
            num_cycles: Number of times to repeat the program

        Returns:
            List of UpcomingWorkoutCreate objects

        Raises:
            LiftoscriptParseError: If validation fails or syntax is invalid
        """
        self._parse_required_comments(script)

        lines = script.strip().split("\n")
        all_workouts = []
        sessions_per_cycle = 0

        for cycle in range(num_cycles):
            session_offset = cycle * sessions_per_cycle
            cycle_workouts, sessions_in_cycle = self._parse_script(lines, cycle, session_offset)
            sessions_per_cycle = max(sessions_in_cycle, sessions_per_cycle)
            all_workouts.extend(cycle_workouts)

        return all_workouts
