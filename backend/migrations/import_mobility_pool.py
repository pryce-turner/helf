"""One-shot import of a mobility Overview.md into `exercises`.

Plan 0012 §1 moved the mobility reference layer into helf. This is the move:
each `### Movement` block in the Obsidian note becomes one `exercises` row with
`is_mobility = 1`, its markdown body in `notes`, and its Enjoyment stars in
`rating`.

**A script, not a migration.** The tests run the real migrations against a
temporary database (`conftest` does `upgrade head`), so a migration carrying
this data would inject eighteen movements and their prose into every test run.
Nothing in the read path depends on the pool existing — unlike the `metric_def`
vocabulary, which is why *that* is seeded by migration. Follows the precedent
of `tinydb_to_sqlite.py`: a one-shot import lives here and is run by hand.

**Exact name matches are updated; everything else is created and reported.**
The vault's own rule is to flag rather than silently merge, and it is right:
"Standing Good Morning" and the existing "Good Morning" are almost certainly
one movement, but "Calf Raise" against five logged calf variants is not a call
a string comparison should make. Near-matches are printed for a human to merge
deliberately, and nothing is renamed.

    python migrations/import_mobility_pool.py            # dry run
    python migrations/import_mobility_pool.py --apply

Back up first — `sqlite3 data/helf.db ".backup data/helf.db.bak"`. `cp` is not
a consistent copy with WAL on.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app import database  # noqa: E402
from app.db.models import Category, Exercise  # noqa: E402
from app.utils.date_helpers import get_current_datetime  # noqa: E402

DEFAULT_SOURCE = (
    Path.home() / "Documents/PryceVault/Lifting/Mobility/Lower Back/Overview.md"
)

# The one thing the markdown cannot supply. A movement has exactly one category
# and Overview does not record it, because in the vault the region *was* the
# grouping — `is_mobility` is what carries "this is mobility work" here, and
# the category goes on saying which part of the body it trains.
CATEGORIES = {
    "90/90 Hip Flexor Stretch": "Legs",
    "QL Raise": "Core",
    "Standing Good Morning": "Back",
    "Jefferson Curl": "Back",
    "Deficit Reverse Lunge": "Legs",
    "Weighted Hip Raise": "Legs",
    "Weighted Deep Squat Knee Driver": "Legs",
    "Side Plank Weighted Hip Circles": "Core",
    "Hanging Knee Raise": "Core",
    "Bench Banded Adductor Rotation": "Legs",
    "Copenhagen Raise": "Core",
    "Decline Bicycle Crunch": "Core",
    "Offset Weight Back Extension": "Back",
    "Calf Raise": "Legs",
    "Weighted Pigeon Squat": "Legs",
    "Weighted Dynamic Couch Stretch": "Legs",
    "Weighted Butterfly": "Legs",
    "Deep Goblet Squat": "Legs",
}

FALLBACK_CATEGORY = "Core"

BLOCK = re.compile(r"^### (.+?)$\n(.*?)(?=^### |\Z)", re.MULTILINE | re.DOTALL)
ENJOYMENT = re.compile(r"^\*\*Enjoyment:\*\*\s*(.+?)$", re.MULTILINE)


@dataclass
class Movement:
    name: str
    rating: int | None
    notes: str


def parse(markdown: str) -> list[Movement]:
    """Pull one Movement out of each `### ` block."""
    movements: list[Movement] = []

    for match in BLOCK.finditer(markdown):
        name = match.group(1).strip()
        body = match.group(2)

        rating = None
        enjoyment = ENJOYMENT.search(body)
        if enjoyment:
            # Stars are the rating. "_unrated_" has none, which is NULL rather
            # than zero — never rated and rated badly are different facts, and
            # the CHECK bounds the column at 1..5 so zero cannot be stored.
            stars = enjoyment.group(1).count("★")
            rating = stars or None
            # The Enjoyment line itself does not go into `notes`: it is the
            # `rating` column now, and keeping both would let them disagree.
            body = body[: enjoyment.start()] + body[enjoyment.end() :]

        movements.append(Movement(name=name, rating=rating, notes=body.strip()))

    return movements


def _near_matches(name: str, existing: dict[str, str]) -> list[str]:
    """Existing exercises whose name contains, or is contained by, `name`.

    Containment rather than shared words. Sharing a word is worthless here —
    "Offset Weight Back Extension" shares one with eleven triceps movements —
    whereas containment finds the pairs actually worth a human's attention:
    "Standing Good Morning" over "Good Morning", "Calf Raise" under "Single Leg
    Calf Raise". Matched on word boundaries so "Crunch" does not pull in
    "Crunches".

    This only ever prints. Nothing is merged or renamed by this script.
    """
    lowered_name = name.lower()

    def contains(haystack: str, needle: str) -> bool:
        return re.search(rf"\b{re.escape(needle)}\b", haystack) is not None

    return [
        original
        for lowered, original in existing.items()
        if lowered != lowered_name
        and (contains(lowered, lowered_name) or contains(lowered_name, lowered))
    ]


def run(source: Path, apply: bool) -> int:
    movements = parse(source.read_text())
    if not movements:
        print(f"No `### ` movement blocks found in {source}", file=sys.stderr)
        return 1

    created, updated, flagged = [], [], []

    with database.SessionLocal() as session:
        existing = {
            e.name.lower(): e.name
            for e in session.execute(select(Exercise)).scalars().all()
        }

        for movement in movements:
            category_name = CATEGORIES.get(movement.name, FALLBACK_CATEGORY)

            exercise = session.execute(
                select(Exercise).where(Exercise.name == movement.name)
            ).scalar_one_or_none()
            if exercise is None:
                # Case-insensitively, because SQLite's default collation is
                # case-sensitive and UNIQUE(name) would not have caught it.
                exercise = session.execute(
                    select(Exercise).where(
                        Exercise.name.collate("NOCASE") == movement.name
                    )
                ).scalar_one_or_none()

            if exercise is not None:
                exercise.notes = movement.notes
                exercise.rating = movement.rating
                exercise.is_mobility = True
                updated.append(exercise.name)
                continue

            category = session.execute(
                select(Category).where(Category.name == category_name)
            ).scalar_one_or_none()
            if category is None:
                category = Category(
                    name=category_name, created_at=get_current_datetime()
                )
                session.add(category)
                session.flush()

            session.add(
                Exercise(
                    name=movement.name,
                    category_id=category.id,
                    notes=movement.notes,
                    rating=movement.rating,
                    is_mobility=True,
                    use_count=0,
                    created_at=get_current_datetime(),
                )
            )
            created.append(movement.name)

            for near in _near_matches(movement.name, existing):
                flagged.append((movement.name, near))

        if apply:
            session.commit()
        else:
            session.rollback()

    verb = "Imported" if apply else "Would import"
    print(f"{verb} {len(movements)} movements from {source}")
    print(f"  updated in place : {len(updated)}")
    for name in updated:
        print(f"      {name}")
    print(f"  created          : {len(created)}")
    for name in created:
        print(f"      {name}")

    if flagged:
        print("\n  Possible duplicates — merge by hand if they are the same movement:")
        for new, near in flagged:
            print(f"      {new!r} resembles existing {near!r}")

    if not apply:
        print("\nDry run. Re-run with --apply to write.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--apply", action="store_true", help="write to the database")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"No such file: {args.source}", file=sys.stderr)
        return 1

    return run(args.source, args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
