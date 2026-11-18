"""One-shot seed of the movement break pool: equipment-free movements, and their bouts.

**A script, not a migration**, following `import_mobility_pool.py` and for the
same two reasons. The tests migrate a temporary database from scratch
(`conftest` does `upgrade head`), so a migration carrying this data would
inject twenty-eight movements and their prose into every test run and break
the tests that assert on the category list. And every insert here fires an
audit trigger, so migration-seeded movements would write audit rows on every
fresh install, attributed to whoever ran the migration. Nothing in the read
path depends on the pool having members.

    cd backend
    .venv/bin/python migrations/seed_movement_break_pool.py            # dry run
    .venv/bin/python migrations/seed_movement_break_pool.py --apply

**A movement is created only if nothing of that name exists**, and one that
exists is never given `form` text it already has. The enpool sets
`movement_break_seconds` only where it is still NULL, so running this twice — or
running it after the user has curated the pool — changes nothing.

`application` and `rating` are left NULL for the new movements, which is the
honest value: nothing has been learned about these yet, and a guess in
`application` is indistinguishable from a lesson (e2b9c4d17a05 split the two
fields precisely for that). A rating is only ever written from a direct
statement of liking, and none has been made.

The `form` text is written to be **corrected rather than trusted** — it is
setup cues in the voice of the existing rows, in the same field the Exercises
page edits, so a wrong cue is one edit away from being right.

Back up first: `scripts/backup-db.sh pre-movement-break-seed`. `cp` is not a
consistent copy with WAL on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app import database  # noqa: E402
from app.db.models import Category, Exercise  # noqa: E402
from app.utils.date_helpers import get_current_datetime  # noqa: E402

# (name, category, seconds, form). Seconds is the movement's default bout: a
# hold is 40, a movement with reps in it is 30. Long enough to work, short
# enough to do between tasks without changing clothes.
POOL: list[tuple[str, str, int, str]] = [
    # --- Legs: loaded stretching through the hip, ankle and calf.
    (
        "Deep Squat Hold",
        "Legs",
        40,
        "Feet just outside shoulder width, toes turned out. Sink all the way "
        "down and stay there: elbows inside the knees, pressing them out, "
        "chest up, weight over the middle of the foot. Breathe behind the "
        "knees; do not bounce.",
    ),
    (
        "Cossack Squat",
        "Legs",
        40,
        "Feet wide, toes forward. Shift onto one leg - that knee bends and "
        "travels over the toes while the other leg stays straight with the toe "
        "up. Sit into the bent hip rather than folding forward. Half the time "
        "each side.",
    ),
    (
        "Hip Airplane",
        "Legs",
        40,
        "Standing on one leg, hinge at the hip until the torso is near "
        "parallel, then rotate the torso open and closed over the standing "
        "leg. Standing knee soft, foot flat. Slow - the rotation is the point, "
        "not the hinge.",
    ),
    (
        "Single-Leg Hinge Reach",
        "Legs",
        40,
        "Standing on one leg with a soft knee, hinge at the hip and reach for "
        "the floor in front of the standing foot; the free leg "
        "counterbalances behind. Hinge, do not curl - the back stays long. "
        "Half the time each side.",
    ),
    (
        "Wall Sit",
        "Legs",
        40,
        "Back flat to a wall, knees over the ankles, at whatever depth keeps "
        "the thighs above parallel. Hands off the legs. The legs decide how "
        "long, not the clock.",
    ),
    (
        "Standing Calf Raise",
        "Legs",
        30,
        "One foot, barefoot or in socks. Rise as high onto the toes as it "
        "goes, pause at the top, then lower over three full seconds. The "
        "lowering is the working part.",
    ),
    (
        "Knee-to-Wall Ankle Mobilisation",
        "Legs",
        30,
        "Toe a hand-width from a wall. Drive the knee to the wall without the "
        "heel lifting. Back the foot off if the heel has to come up to get "
        "there - the heel stays down, or the ankle is not moving.",
    ),
    (
        "Chair Pigeon",
        "Legs",
        40,
        "Sitting upright on a chair, one ankle across the opposite thigh just "
        "above the knee. Keep the shin parallel to the floor and hinge forward "
        "from the hips with a flat back - the fold is at the hip, not in the "
        "spine. Half the time each side.",
    ),
    (
        "Seated Figure-Four",
        "Legs",
        30,
        "Sitting tall on a chair, one ankle over the opposite knee. Lean "
        "forward until it lands in the glute of the crossed leg. A flat back "
        "keeps it in the hip. Half the time each side.",
    ),
    (
        "World's Greatest Stretch",
        "Legs",
        40,
        "From a long lunge, both hands inside the front foot, back knee down. "
        "Elbow to the inside of the front ankle, then rotate that same arm "
        "open to the ceiling and follow it with the eyes. Alternate sides.",
    ),
    # --- Core: standing and seated, so it can be done in office clothes.
    (
        "Standing Thoracic Rotation",
        "Core",
        30,
        "Feet hip width, hands behind the head, elbows wide. Rotate through "
        "the upper back - the ribcage turns, the hips do not. The arms come "
        "along rather than leading.",
    ),
    (
        "Standing Side Bend",
        "Core",
        30,
        "One hand overhead, the other at the hip. Reach up and over without "
        "leaning forwards or back - the bend stays in the frontal plane. "
        "Exhale into the short side.",
    ),
    (
        "Standing Hip Hike",
        "Core",
        30,
        "Standing on one leg, drop the free hip and then lift it towards the "
        "ribs without leaning the torso. The hip comes up; the shoulder does "
        "not come down.",
    ),
    # --- Back and shoulders: the two things an office undoes.
    (
        "Chin Tuck",
        "Back",
        30,
        "Sitting or standing tall, draw the chin straight back to make a "
        "second chin, without tipping the head. Hold a second, release. Small "
        "and slow; no nodding.",
    ),
    (
        "Thoracic Extension Over Chair",
        "Back",
        30,
        "Sit forward on a chair, hands behind the head, elbows together. "
        "Extend back over the backrest, lifting the sternum and opening the "
        "elbows. The bend travels along the whole spine - do not just drop the "
        "head.",
    ),
    (
        "Wall Angel",
        "Shoulders",
        40,
        "Back, hips and head against a wall, arms in a goalpost with the backs "
        "of the hands on it. Slide the hands up and down keeping all three "
        "contact points - the hands leave the wall the moment the range is "
        "borrowed from the lower back.",
    ),
    (
        "Scapular Push-Up",
        "Shoulders",
        30,
        "Hands on a desk or a wall, arms straight. Without bending the arms, "
        "sink the chest between the shoulder blades and then push them apart. "
        "Small range, all of it at the shoulder blade.",
    ),
    # --- Arms: the one thing a keyboard costs.
    (
        "Wrist Extension Stretch",
        "Arms",
        30,
        "Arm straight in front, fingers pointing down, the other hand drawing "
        "them back towards the elbow. Elbow stays locked and the shoulder "
        "stays down. Half the time each side.",
    ),
]

# Movements already in the catalog that need no equipment. Enpooled rather than
# re-created, so their history and whatever `form` they carry survive.
# Crunch and Bicycle Crunch are equipment-free and left out on purpose: they
# are ab work rather than mobility, and the pool is not the ab catalog.
EXISTING: list[tuple[str, int]] = [
    ("Pushup", 30),
    ("Plank", 30),
    ("Side Plank", 30),
    ("Dead Bug", 40),
    ("Chair Knee Twist", 40),
    ("Chair Leg Raise", 30),
    ("Thread the Needle", 40),
    ("Side-Lying Hip Circle", 30),
    ("Glute Circles", 40),
    ("Bench Dip", 30),
]


def seed(apply: bool) -> int:
    created = 0
    enpooled = 0
    skipped: list[str] = []

    with database.SessionLocal() as session:
        for name, category_name, seconds, form in POOL:
            existing = session.execute(
                select(Exercise).where(Exercise.name == name)
            ).scalar_one_or_none()

            if existing:
                if existing.form:
                    skipped.append(f"{name} (exists, form left alone)")
                else:
                    existing.form = form
                    skipped.append(f"{name} (exists, form filled in)")
                if existing.movement_break_seconds is None:
                    existing.movement_break_seconds = seconds
                    enpooled += 1
                continue

            category = session.execute(
                select(Category).where(Category.name == category_name)
            ).scalar_one_or_none()
            if not category:
                category = Category(
                    name=category_name, created_at=get_current_datetime()
                )
                session.add(category)
                session.flush()
                print(f"  + category {category_name}")

            session.add(
                Exercise(
                    name=name,
                    category_id=category.id,
                    form=form,
                    movement_break_seconds=seconds,
                    last_used=None,
                    use_count=0,
                    created_at=get_current_datetime(),
                )
            )
            created += 1

        for name, seconds in EXISTING:
            exercise = session.execute(
                select(Exercise).where(Exercise.name == name)
            ).scalar_one_or_none()
            if not exercise:
                skipped.append(f"{name} (not in this catalog, skipped)")
                continue
            if exercise.movement_break_seconds is not None:
                continue
            exercise.movement_break_seconds = seconds
            enpooled += 1

        # `SessionLocal` is `autoflush=False`, so the count has to ask for a
        # flush or it reports the pool as it was before this script ran.
        session.flush()
        total = session.execute(
            select(Exercise).where(Exercise.movement_break_seconds.is_not(None))
        ).scalars().all()
        print(f"  created {created}, enpooled {enpooled}, pool now {len(total)}")
        for line in skipped:
            print(f"  ~ {line}")

        if apply:
            session.commit()
            print("  committed")
        else:
            session.rollback()
            print("  rolled back (dry run — pass --apply to write)")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply", action="store_true", help="write to the database"
    )
    parser.add_argument("--db", default=None, help="path to the database")
    args = parser.parse_args()

    if args.db:
        database.settings.db_path = Path(args.db)

    print(f"movement break pool seed: {database.settings.db_path}")
    if not args.apply:
        print("dry run")
    return seed(args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
