"""Every built-in program parses, and the core-stability one has its shape."""

from pathlib import Path

import pytest

from app.api.upcoming import PRESETS
from app.services.library_service import resolve_block
from app.services.liftoscript_service import LiftoscriptParser

PRESET_DIR = Path(__file__).resolve().parents[1] / "app" / "presets"


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_every_builtin_program_parses(name):
    script = (PRESET_DIR / f"{name}.liftoscript").read_text()
    assert LiftoscriptParser().parse(script, resolve_block=resolve_block)


def test_core_stability_531_runs_each_day_in_order():
    script = (PRESET_DIR / "core_stability_531.liftoscript").read_text()
    sets = LiftoscriptParser().parse(script, resolve_block=resolve_block)
    sessions = sorted({s.session for s in sets})
    assert len(sessions) == 16  # 4 days x 4 weeks

    week1_press = [s for s in sets if s.session == 1]
    names = list(dict.fromkeys(s.exercise for s in week1_press))
    # Dynamic stretching, core, main lift, accessories, foam roll, static.
    assert names.index("Arm Circles") < names.index("Side Plank Leg Lift")
    assert names.index("6 Position Carry Drill") < names.index("Overhead Press")
    assert names.index("Overhead Press") < names.index("Pull Up")
    assert names.index("Cable Face Pull") < names.index("Foam Roll Thoracic Spine")
    assert names[-1] == "Thoracic Extension Over Chair"

    press = [s for s in week1_press if s.exercise == "Overhead Press"]
    assert [s.weight for s in press] == [80, 90, 100]  # 65/75/85% of a 120 TM
    assert press[-1].comment == "AMRAP"

    carry = next(s for s in week1_press if s.exercise == "6 Position Carry Drill")
    assert (carry.weight, carry.reps, carry.work_seconds, carry.rest_seconds, carry.rest_after_seconds) == (35, 6, 30, 10, 90)


def test_each_day_has_its_core_pair():
    script = (PRESET_DIR / "core_stability_531.liftoscript").read_text()
    sets = LiftoscriptParser().parse(script, resolve_block=resolve_block)
    by_session: dict[int, set[str]] = {}
    for s in sets:
        by_session.setdefault(s.session, set()).add(s.exercise)
    pairs = {
        "Overhead Press": {"6 Position Carry Drill", "Side Plank Leg Lift"},
        "Flat Barbell Bench Press": {"Milco Bench Press", "Ab-Wheel Rollout"},
        "Deadlift": {"Renegade Rows", "Around the Worlds"},
        "Barbell Squat": {"Stir The Pot", "Cable Chops and Lifts"},
    }
    for exercises in by_session.values():
        (lift,) = [m for m in pairs if m in exercises]
        assert pairs[lift] <= exercises


def test_the_mobility_blocks_are_flagged_and_the_training_is_not():
    script = (PRESET_DIR / "core_stability_531.liftoscript").read_text()
    week1_press = [s for s in LiftoscriptParser().parse(script, resolve_block=resolve_block) if s.session == 1]
    flagged = {s.exercise for s in week1_press if s.is_mobility}
    unflagged = {s.exercise for s in week1_press if not s.is_mobility}
    assert flagged == {
        "Arm Circles", "Cat-Cow", "Standing Thoracic Rotation", "World's Greatest Stretch",
        "Foam Roll Thoracic Spine", "Foam Roll Lats",
        "Doorway Pec Stretch", "Thoracic Extension Over Chair",
    }
    assert unflagged == {
        "Side Plank Leg Lift", "6 Position Carry Drill", "Overhead Press",
        "Pull Up", "Cable Face Pull", "Lateral Dumbbell Raise",
    }

