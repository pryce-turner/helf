"""The library: blocks and programs, yours and built-in, all of it script (plan 0022).

A **block** is part of a day - sets with no `## Day` headers. Yours are the
hand-built presets (`workout_preset` rows, edited set by set on the day
editor); built-in ones are files in `app/presets/blocks/`. A **program** is
days, often weeks - built-in ones are `app/presets/*.liftoscript`, yours are
`workout_program` rows. A program pulls a block in with a `[Block name]` line.

Rows stay the storage for your blocks: the day editor is the better place to
build one, and `preset_to_script` makes the script a lossless view of it.
"""

from pathlib import Path

from app.repositories.preset_repo import PresetRepository
from app.services.liftoscript_service import LiftoscriptParser

BLOCK_DIR = Path(__file__).resolve().parent.parent / "presets" / "blocks"

#: Built-in blocks: file stem -> name used in `[...]`. Names are reserved -
#: a block of yours cannot take one, so an include never means two things.
BUILTIN_BLOCKS: dict[str, str] = {
    "press_warmup": "Press warm-up",
    "press_core": "Press core",
    "upper_cooldown_press": "Press cool-down",
    "deadlift_warmup": "Deadlift warm-up",
    "deadlift_core": "Deadlift core",
    "lower_cooldown_deadlift": "Deadlift cool-down",
    "bench_warmup": "Bench warm-up",
    "bench_core": "Bench core",
    "upper_cooldown_bench": "Bench cool-down",
    "squat_warmup": "Squat warm-up",
    "squat_core": "Squat core",
    "lower_cooldown_squat": "Squat cool-down",
}
BUILTIN_BLOCK_BY_NAME = {name.lower(): stem for stem, name in BUILTIN_BLOCKS.items()}


def builtin_block_script(name: str) -> str | None:
    stem = BUILTIN_BLOCK_BY_NAME.get(name.strip().lower())
    if stem is None:
        return None
    return (BLOCK_DIR / f"{stem}.liftoscript").read_text()


def is_reserved_block_name(name: str) -> bool:
    return name.strip().lower() in BUILTIN_BLOCK_BY_NAME


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _duration(seconds: int) -> str:
    return f"{seconds}s"


def item_spec(item: dict) -> str:
    """One preset tile as a set spec, without the leading `NxM`."""
    parts: list[str] = []
    if item.get("weight") is not None:
        parts.append(f"{_fmt(item['weight'])}lb")
    if item.get("work_seconds") is not None:
        parts.append(_duration(item["work_seconds"]))
    if item.get("rest_seconds"):
        parts.append(f"rest {_duration(item['rest_seconds'])}")
    if item.get("rest_after_seconds"):
        parts.append(f"after {_duration(item['rest_after_seconds'])}")
    if item.get("distance") is not None:
        parts.append(f"{_fmt(item['distance'])}{item.get('distance_unit') or 'm'}")
    if item.get("is_mobility"):
        parts.append("~")
    if item.get("comment"):
        # A quote cannot hold a quote; the script has no escape for one.
        parts.append('"' + item["comment"].replace('"', "'") + '"')
    return " ".join(parts)


def preset_to_script(preset: dict) -> str:
    """A block of yours as script: one line per run of identical sets.

    Consecutive tiles with the same exercise and targets fold into `NxM`,
    which is how the block reads back to a person. A tile with no rep count
    is written `1x1` - the script has no way to say "uncounted".
    """
    lines: list[str] = []
    run: list[tuple[str, int, str]] = []  # (exercise, reps, spec) for the current run

    def flush() -> None:
        if run:
            exercise, reps, spec = run[0]
            line = f"{exercise} / {len(run)}x{reps}"
            lines.append(f"{line} {spec}".rstrip())
            run.clear()

    for item in sorted(preset["items"], key=lambda i: i["order"]):
        key = (item["exercise"], item.get("reps") or 1, item_spec(item))
        if run and run[0] != key:
            flush()
        run.append(key)
    flush()
    return "\n".join(lines) + ("\n" if lines else "")


def resolve_block(name: str) -> str | None:
    """`[Name]` -> script: a built-in block, else one of yours by name."""
    builtin = builtin_block_script(name)
    if builtin is not None:
        return builtin
    for preset in PresetRepository().get_all():
        if preset["name"].strip().lower() == name.strip().lower():
            return preset_to_script(preset)
    return None


def block_script_to_items(script: str) -> list[dict]:
    """A block's script as preset tiles, for "Duplicate to edit"."""
    # A block has no day header; give it one so the parser has a session.
    sets = LiftoscriptParser().parse("## Block\n" + script, resolve_block=resolve_block)
    return [
        {
            "exercise": s.exercise,
            "category": s.category,
            "weight": s.weight,
            "reps": s.reps,
            "distance": s.distance,
            "distance_unit": s.distance_unit,
            "comment": s.comment,
            "is_mobility": s.is_mobility,
            "work_seconds": s.work_seconds,
            "rest_seconds": s.rest_seconds,
            "rest_after_seconds": s.rest_after_seconds,
        }
        for s in sets
    ]
