"""Tests for liftoscript_service.py - Liftoscript parser."""

import pytest

from app.services.liftoscript_service import (
    LiftoscriptParser,
    LiftoscriptParseError,
    EXERCISE_CATEGORIES,
)


class TestLiftoscriptParser:
    """Tests for LiftoscriptParser."""

    def test_parse_simple_absolute_weight(self):
        """Test parsing simple exercise with absolute weight."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Barbell Squat / 3x5 135lb
"""
        workouts = parser.parse(script)

        assert len(workouts) == 3  # 3 sets
        assert workouts[0].exercise == "Barbell Squat"
        assert workouts[0].category == "Legs"
        assert workouts[0].weight == 135
        assert workouts[0].weight_unit == "lbs"
        assert workouts[0].reps == 5
        assert workouts[0].session == 1

    def test_parse_weight_in_kg_converts_to_lbs(self):
        """Test that kg weights are converted to lbs."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Deadlift / 1x5 100kg
"""
        workouts = parser.parse(script)

        assert len(workouts) == 1
        assert workouts[0].weight == 220  # 100kg ≈ 220.46lbs, rounded
        assert workouts[0].weight_unit == "lbs"

    def test_parse_percentage_weight_with_1rm_comment(self):
        """Test parsing percentage-based weight with required 1RM comment."""
        parser = LiftoscriptParser()
        script = """
// Flat Barbell Bench Press 1RM: 200lb
## Day 1
Flat Barbell Bench Press / 3x5 75%
"""
        workouts = parser.parse(script)

        assert len(workouts) == 3
        # 75% of 200 = 150, rounded to nearest 5
        assert workouts[0].weight == 150
        assert workouts[0].weight_unit == "lbs"

    def test_parse_percentage_without_1rm_raises_error(self):
        """Test that using percentage without 1RM comment raises error."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Flat Barbell Bench Press / 3x5 75%
"""
        with pytest.raises(LiftoscriptParseError) as exc_info:
            parser.parse(script)

        assert "missing required comment" in str(exc_info.value).lower()
        assert "1RM" in str(exc_info.value)

    def test_parse_linear_progression_with_sw_comment(self):
        """Test linear progression with starting weight comment."""
        parser = LiftoscriptParser()
        script = """
// Barbell Squat SW: 135lb
## Day 1
Barbell Squat / 3x5 progress: lp(5lb)
"""
        # First cycle: 135 + (5 * 0) = 135
        workouts = parser.parse(script, num_cycles=1)
        assert workouts[0].weight == 135

        # Second cycle should add 5lbs
        workouts = parser.parse(script, num_cycles=2)
        # First cycle: 135, Second cycle: 140
        assert workouts[3].weight == 140

    def test_parse_linear_progression_without_sw_raises_error(self):
        """Test that using linear progression without SW comment raises error."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Barbell Squat / 3x5 progress: lp(5lb)
"""
        with pytest.raises(LiftoscriptParseError) as exc_info:
            parser.parse(script)

        assert "missing required comment" in str(exc_info.value).lower()
        assert "SW" in str(exc_info.value)

    def test_parse_amrap_sets(self):
        """Test parsing AMRAP sets (marked with +)."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Pull Ups / 3x10+ 0lb
"""
        workouts = parser.parse(script)

        assert len(workouts) == 3
        for workout in workouts:
            assert workout.comment == "AMRAP"
            assert workout.reps == 10

    def test_parse_multiple_set_specifications(self):
        """Test parsing multiple set specs separated by commas."""
        parser = LiftoscriptParser()
        script = """
// Deadlift 1RM: 315lb
## Day 1
Deadlift / 1x5 65%, 1x3 80%, 1x1+ 95%
"""
        workouts = parser.parse(script)

        # Should have 1 + 1 + 1 = 3 total sets
        assert len(workouts) == 3

        # First set: 65% of 315 = 204.75 → 205
        assert workouts[0].reps == 5
        assert workouts[0].weight == 205

        # Second set: 80% of 315 = 252
        assert workouts[1].reps == 3
        assert workouts[1].weight == 250

        # Third set: 95% of 315 = 299.25 → 300, AMRAP
        assert workouts[2].reps == 1
        assert workouts[2].weight == 300
        assert workouts[2].comment == "AMRAP"

    def test_parse_multiple_days(self):
        """Test parsing multiple day headers."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Barbell Squat / 3x5 135lb

## Day 2
Flat Barbell Bench Press / 3x8 100lb
"""
        workouts = parser.parse(script)

        # 3 sets from day 1 + 3 sets from day 2 = 6 total
        assert len(workouts) == 6

        # First 3 should be session 1
        assert all(w.session == 1 for w in workouts[:3])
        assert all(w.exercise == "Barbell Squat" for w in workouts[:3])

        # Last 3 should be session 2
        assert all(w.session == 2 for w in workouts[3:])
        assert all(w.exercise == "Flat Barbell Bench Press" for w in workouts[3:])

    def test_parse_multiple_exercises_same_day(self):
        """Test parsing multiple exercises in the same day."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Barbell Squat / 3x5 135lb
Flat Barbell Bench Press / 3x8 100lb
"""
        workouts = parser.parse(script)

        # All should be in session 1
        assert all(w.session == 1 for w in workouts)
        assert len(workouts) == 6

        # First 3 are squats, last 3 are bench
        assert workouts[0].exercise == "Barbell Squat"
        assert workouts[3].exercise == "Flat Barbell Bench Press"

    def test_parse_exercise_without_category_defaults_to_other(self):
        """Test that exercises not in EXERCISE_CATEGORIES default to 'Other'."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Unknown Exercise / 3x10 50lb
"""
        workouts = parser.parse(script)

        assert workouts[0].category == "Other"

    def test_parse_ignores_comments(self):
        """Test that comment lines starting with // are ignored."""
        parser = LiftoscriptParser()
        script = """
// This is a comment
// Another comment
## Day 1
// Inline comment
Barbell Squat / 3x5 135lb
"""
        workouts = parser.parse(script)

        assert len(workouts) == 3

    def test_parse_ignores_blank_lines(self):
        """Test that blank lines are ignored."""
        parser = LiftoscriptParser()
        script = """

## Day 1

Barbell Squat / 3x5 135lb

"""
        workouts = parser.parse(script)

        assert len(workouts) == 3

    def test_parse_multiple_cycles(self):
        """Test parsing with multiple cycles."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Barbell Squat / 2x5 135lb
## Day 2
Flat Barbell Bench Press / 2x5 100lb
"""
        workouts = parser.parse(script, num_cycles=3)

        # 2 days × 2 sets × 3 cycles = 12 total sets
        assert len(workouts) == 12

        # First cycle: sessions 1-2
        cycle_1 = [w for w in workouts if w.session in [1, 2]]
        assert len(cycle_1) == 4

        # Second cycle: sessions 3-4
        cycle_2 = [w for w in workouts if w.session in [3, 4]]
        assert len(cycle_2) == 4

        # Third cycle: sessions 5-6
        cycle_3 = [w for w in workouts if w.session in [5, 6]]
        assert len(cycle_3) == 4

    def test_parse_multiple_cycles_with_linear_progression(self):
        """Test that linear progression increments across cycles."""
        parser = LiftoscriptParser()
        script = """
// Barbell Squat SW: 100lb
## Day 1
Barbell Squat / 1x5 progress: lp(10lb)
"""
        workouts = parser.parse(script, num_cycles=3)

        assert len(workouts) == 3
        # Cycle 0: 100 + (10 * 0) = 100
        assert workouts[0].weight == 100
        # Cycle 1: 100 + (10 * 1) = 110
        assert workouts[1].weight == 110
        # Cycle 2: 100 + (10 * 2) = 120
        assert workouts[2].weight == 120

    def test_parse_invalid_sets_reps_format_raises_error(self):
        """Test that invalid sets/reps format raises error."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Barbell Squat / 3sets5reps 135lb
"""
        with pytest.raises(LiftoscriptParseError) as exc_info:
            parser.parse(script)

        assert "Invalid sets/reps format" in str(exc_info.value)

    def test_parse_1rm_comment_with_kg(self):
        """Test that 1RM comments in kg are converted to lbs."""
        parser = LiftoscriptParser()
        script = """
// Deadlift 1RM: 140kg
## Day 1
Deadlift / 1x5 80%
"""
        workouts = parser.parse(script)

        # 140kg ≈ 308.64lbs, 80% = 246.91, rounded to 245
        assert workouts[0].weight == 245

    def test_parse_sw_comment_with_kg(self):
        """Test that SW comments in kg are converted to lbs."""
        parser = LiftoscriptParser()
        script = """
// Barbell Squat SW: 60kg
## Day 1
Barbell Squat / 1x5 progress: lp(2.5kg)
"""
        workouts = parser.parse(script, num_cycles=2)

        # 60kg ≈ 132.28lbs, 2.5kg ≈ 5.51lbs
        # Cycle 0: 132.28 + (5.51 * 0) = 132.28, rounded to 130
        assert workouts[0].weight == 130
        # Cycle 1: 132.28 + (5.51 * 1) = 137.79, rounded to 140
        assert workouts[1].weight == 140

    def test_parse_weight_rounding_to_nearest_5(self):
        """Test that weights are rounded to nearest 5 for barbell loading."""
        parser = LiftoscriptParser()
        script = """
// Flat Barbell Bench Press 1RM: 203lb
## Day 1
Flat Barbell Bench Press / 1x5 77%
"""
        workouts = parser.parse(script)

        # 77% of 203 = 156.31, should round to 155
        assert workouts[0].weight == 155

    def test_parse_empty_script_returns_empty_list(self):
        """Test that an empty script returns an empty list."""
        parser = LiftoscriptParser()
        script = ""
        workouts = parser.parse(script)

        assert workouts == []

    def test_parse_script_with_only_comments_returns_empty_list(self):
        """Test that a script with only comments returns empty list."""
        parser = LiftoscriptParser()
        script = """
// Comment 1
// Comment 2
// Comment 3
"""
        workouts = parser.parse(script)

        assert workouts == []

    def test_parse_line_without_slash_is_ignored(self):
        """Test that lines without / separator are ignored."""
        parser = LiftoscriptParser()
        script = """
## Day 1
This line has no slash
Barbell Squat / 3x5 135lb
"""
        workouts = parser.parse(script)

        # Should only parse the valid line
        assert len(workouts) == 3

    def test_parse_exercise_with_no_weight(self):
        """Test parsing exercise without weight specification."""
        parser = LiftoscriptParser()
        script = """
## Day 1
Pull Ups / 3x10
"""
        workouts = parser.parse(script)

        assert len(workouts) == 3
        assert workouts[0].weight is None
        assert workouts[0].weight_unit == "lbs"

    def test_exercise_categories_mapping(self):
        """Test that EXERCISE_CATEGORIES contains expected exercises."""
        assert "Barbell Squat" in EXERCISE_CATEGORIES
        assert EXERCISE_CATEGORIES["Barbell Squat"] == "Legs"
        assert EXERCISE_CATEGORIES["Flat Barbell Bench Press"] == "Chest"
        assert EXERCISE_CATEGORIES["Deadlift"] == "Back"
        assert EXERCISE_CATEGORIES["Overhead Press"] == "Triceps"

    def test_convert_kg_to_lbs(self):
        """Test kg to lbs conversion."""
        parser = LiftoscriptParser()
        assert parser._convert_kg_to_lbs(100) == pytest.approx(220.462, rel=0.001)
        assert parser._convert_kg_to_lbs(50) == pytest.approx(110.231, rel=0.001)

    def test_round_to_nearest_5(self):
        """Test rounding to nearest 5."""
        parser = LiftoscriptParser()
        assert parser._round_to_nearest_5(137) == 135
        assert parser._round_to_nearest_5(138) == 140
        assert parser._round_to_nearest_5(140) == 140
        # Python uses banker's rounding: round(28.5) = 28 (rounds to even)
        assert parser._round_to_nearest_5(142.5) == 140
        # Verify it rounds up for .5 when the result is odd
        assert parser._round_to_nearest_5(147.5) == 150
