"""One-shot backfill of the four mobility sessions that only exist as markdown.

Plan 0012 §8 left these out, and the reason was honest: the vault's session
notes record *some* numbers and not others, so a backfill has to invent the
rest. This does it anyway, with the invention labelled.

**Three tiers of number, and they must stay distinguishable.**

1. **Stated.** The user wrote it down — "8 and then 10 reps on 30lb kb QL
   raise". Carried across verbatim, with their own words in the set's comment.
2. **Prescribed.** The routine said 2x8, nothing was said afterwards, so 2x8 is
   what happened. This is the ordinary case and a safe assumption: the notes
   are a list of *deviations*, and a movement listed under "Held unchanged"
   with no feedback is a movement that went to plan.
3. **Inferred.** A number neither stated nor prescribed, reconstructed from
   elsewhere. There are exactly two kinds here and both are recorded in each
   session's note: a bar-only good morning is 45lb and "+15lb plates" is 75lb
   (confirmed by 2026-08-08's stated "75lb x 6 reps x 2 sets"), and the QL
   kettlebell prescribed as "~25-30lb" is taken as 30lb (confirmed by the same
   session's stated "30lb kb QL raise").

**Where a load was never stated and cannot be reconstructed, it is NULL.** An
invented weight is worse than a gap: it becomes a point on a progression chart
and a baseline the next session gets programmed against. The unweighted pigeon
regressions are NULL because they were genuinely unweighted; the calf raise
loads are NULL because nobody wrote them down.

Each day also gets its `mobility_session` marker note (Plan 0012 §3) carrying
the session's rationale from the vault, plus a provenance paragraph saying it
was backfilled and which numbers were inferred. Without the marker,
`read_latest_mobility_session()` cannot see these days at all.

    python migrations/backfill_mobility_sessions.py            # dry run
    python migrations/backfill_mobility_sessions.py --apply

Idempotent: a date that already has a `mobility_session` note is skipped.

Back up first — `sqlite3 data/helf.db ".backup data/helf.db.bak"`.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app import database  # noqa: E402
from app.db.models import Note, Workout  # noqa: E402
from app.models.workout import WorkoutCreate  # noqa: E402
from app.repositories.mobility_repo import NOON, SESSION_KIND  # noqa: E402
from app.repositories.workout_repo import WorkoutRepository  # noqa: E402

PROVENANCE = (
    "\n\nBackfilled 2026-08-11 from the Obsidian session note. Reps and loads "
    "carrying a comment are what the user wrote down; the rest are the "
    "prescription, assumed performed, because the notes record deviations. "
    "A bar-only good morning is taken as 45lb and \"+15lb plates\" as 75lb; "
    "the QL kettlebell prescribed as ~25-30lb is taken as 30lb. Both are "
    "confirmed by 2026-08-08's stated numbers. Loads that were never written "
    "down are NULL rather than guessed."
)


@dataclass
class Set:
    exercise: str
    category: str
    reps: int | None = None
    weight: float | None = None
    comment: str | None = None


@dataclass
class Session:
    date: str
    rationale: str
    sets: list[Set] = field(default_factory=list)


SESSIONS = [
    Session(
        date="2026-06-27",
        rationale=(
            "First session in the program's written record. The Romanian "
            "deadlift is replaced by the standing good morning: the same "
            "hamstring stimulus, but the bar on the back is a longer spinal "
            "lever, so the erectors work to hold neutral. The RDL gave a good "
            "hamstring stretch and little for the back."
        ),
        sets=[
            Set("Hanging Knee Raise", "Core", 12),
            Set("Hanging Knee Raise", "Core", 9,
                comment="only got 9. Full range by tucking the feet behind on "
                        "extension - much better ab stretch"),
            Set("QL Raise", "Core", 10, 40),
            Set("QL Raise", "Core", 4, 40,
                comment="slow and steady with the 40lb kettlebell pushed me to "
                        "failure in 4. Can be done on the same side of the hyper "
                        "machine; worth a plate on the opposite leg for stability"),
            Set("Copenhagen Raise", "Core", 8),
            Set("Copenhagen Raise", "Core", 8,
                comment="leg fully extended and slightly heel-biased to keep "
                        "strain off the knee"),
            Set("Calf Raise", "Legs", 15),
            Set("Calf Raise", "Legs", 15,
                comment="modify these to 2x8, can always up the weight"),
            Set("Standing Good Morning", "Back", 8, 45,
                comment="bar only, 3 sec eccentric"),
            Set("Standing Good Morning", "Back", 8, 75,
                comment="15lb plates for the second set was a good load"),
            Set("Weighted Dynamic Couch Stretch", "Legs", 8, 25),
            Set("Weighted Dynamic Couch Stretch", "Legs", 8, 25,
                comment="25lb dumbbells was great. Roller flipped around against "
                        "the window, level 3 notch, foot in the close corner of "
                        "the tile"),
            Set("Weighted Pigeon Squat", "Legs", 8),
            Set("Weighted Pigeon Squat", "Legs", 8,
                comment="with a kettlebell it's excellent. Keep the bottom deep "
                        "but don't come all the way up, barely past half, like a "
                        "calf raise"),
        ],
    ),
    Session(
        date="2026-08-06",
        rationale=(
            "First session back after a ~6 week gap, so every load was a "
            "ceiling rather than a target. Hanging knee raise 2x12 to 2x10 "
            "after failing at 9; QL down from 40lb, which was a 4-rep failure "
            "and so mis-prescribed for 10s; calf raise 2x15 to 2x8, adding "
            "weight rather than reps. A weighted hip raise joins the routine - "
            "there was no dedicated bilateral hip extension, and it primes the "
            "glutes going into the hinge."
        ),
        sets=[
            Set("Hanging Knee Raise", "Core", 10),
            Set("Hanging Knee Raise", "Core", 10),
            Set("QL Raise", "Core", 8, 30),
            Set("QL Raise", "Core", 8, 30),
            Set("Copenhagen Raise", "Core", 8),
            Set("Copenhagen Raise", "Core", 8),
            Set("Weighted Hip Raise", "Legs", 10,
                comment="did the cable version, not the kettlebell"),
            Set("Weighted Hip Raise", "Legs", 10,
                comment="lots of lower back / hip tendon clicking on the cable "
                        "hip raise. No pain, just annoying, but still a good "
                        "movement I think"),
            Set("Standing Good Morning", "Back", 8, 45,
                comment="bar only, 3 sec eccentric"),
            Set("Standing Good Morning", "Back", 8, 75,
                comment="struggling to find the right spine alignment"),
            Set("Calf Raise", "Legs", 8),
            Set("Calf Raise", "Legs", 8,
                comment="single leg with a dumbbell in the same hand as the "
                        "working calf - keeps the weight over the working foot "
                        "instead of tipping the pelvis"),
            Set("Weighted Dynamic Couch Stretch", "Legs", 8, 25),
            Set("Weighted Dynamic Couch Stretch", "Legs", 8, 25,
                comment="awful but I love it"),
            Set("Weighted Pigeon Squat", "Legs", 8,
                comment="unweighted on the bench, just getting back into it"),
            Set("Weighted Pigeon Squat", "Legs", 8),
        ],
    ),
    Session(
        date="2026-08-07",
        rationale=(
            "Two changes of substance. The hip raise moves to the kettlebell "
            "bridge to get off the clicking - resisted hip *flexion* is what "
            "provokes the snap, and the bridge trains extension instead, which "
            "is also the version relevant to the low back. The good morning "
            "drops to bar only with a bottom pause, so position is the only "
            "thing being trained; position is the limiter, not load."
        ),
        sets=[
            Set("Hanging Knee Raise", "Core", 10),
            Set("Hanging Knee Raise", "Core", 10),
            Set("Decline Bicycle Crunch", "Core", 10, 10,
                comment="doing decline crunch to switch it up, 10lb plate"),
            Set("Decline Bicycle Crunch", "Core", 6, 10,
                comment="6 reps on set 2 to not push the lower back past failure"),
            Set("QL Raise", "Core", 8, 30),
            Set("QL Raise", "Core", 8, 30),
            Set("Copenhagen Raise", "Core", 8),
            Set("Copenhagen Raise", "Core", 8),
            Set("Weighted Hip Raise", "Legs", 10,
                comment="kettlebell on the hips, not the cable"),
            Set("Weighted Hip Raise", "Legs", 10),
            Set("Standing Good Morning", "Back", 8, 45,
                comment="did stiff-leg good mornings because my legs are always "
                        "so tight"),
            Set("Standing Good Morning", "Back", 8, 45,
                comment="felt a good stretch and no pain but felt slightly "
                        "dangerous? Advise"),
            Set("Calf Raise", "Legs", 8),
            Set("Calf Raise", "Legs", 8, comment="same stiff leg. Feeling good"),
            Set("Weighted Dynamic Couch Stretch", "Legs", 8, 30),
            Set("Weighted Dynamic Couch Stretch", "Legs", 8, 30,
                comment="30lbs x 8 x 2, up from 25"),
            Set("Weighted Pigeon Squat", "Legs", 8,
                comment="back on the weighted version, skipped past the "
                        "unweighted regression"),
            Set("Weighted Pigeon Squat", "Legs", 4,
                comment="right side failed after 4 reps while the left held"),
        ],
    ),
    Session(
        date="2026-08-08",
        rationale=(
            "The decline crunch becomes a formal part of the routine at 2x8, "
            "the good morning goes back to soft knees, and the pigeon is "
            "restructured around the right-side asymmetry: both sides drop to "
            "5, the right leads while fresh, and the extra set goes to the "
            "right only. Locking the knees on a good morning caps hip flexion "
            "at hamstring length, so every further inch of descent comes out "
            "of the lumbar spine with a bar on the back - the urge to load "
            "flexion belongs in the Jefferson curl instead."
        ),
        sets=[
            Set("Hanging Knee Raise", "Core", 10),
            Set("Hanging Knee Raise", "Core", 10),
            Set("QL Raise", "Core", 8, 30),
            Set("QL Raise", "Core", 10, 30,
                comment="8 and then 10 reps on the 30lb kb. Up to 35 next"),
            Set("Copenhagen Raise", "Core", 8, 15,
                comment="added a 15lb dumbbell. Hit 8 on the left"),
            Set("Copenhagen Raise", "Core", 7, 15,
                comment="failed on the right side at 7. Will keep this weight"),
            Set("Weighted Hip Raise", "Legs", 8, 30),
            Set("Weighted Hip Raise", "Legs", 7, 30,
                comment="8, and then barely 7 on the 30lb kb raise (not the "
                        "bridge). Not interested in doing the bridge, remove it "
                        "from the program"),
            Set("Standing Good Morning", "Back", 6, 75),
            Set("Standing Good Morning", "Back", 6, 75,
                comment="75lb x 6 reps x 2 sets. Long movement so I'd rather "
                        "increase weight than reps. I feel like pigeon should be "
                        "programmed before to release the glutes a bit?"),
            Set("Calf Raise", "Legs", 10, 40),
            Set("Calf Raise", "Legs", 10, 40, comment="40lb x 10 reps"),
            Set("Weighted Dynamic Couch Stretch", "Legs", 8, 35),
            Set("Weighted Dynamic Couch Stretch", "Legs", 5, 35,
                comment="8 and then 5 reps to failure with the 35s. Keep the "
                        "weight for next time"),
            Set("Weighted Pigeon Squat", "Legs", 5,
                comment="led with the right"),
            Set("Weighted Pigeon Squat", "Legs", 5),
            Set("Weighted Pigeon Squat", "Legs", 5,
                comment="third set on the right only. "
                        "[program] not doing decline bicycle, switching back to "
                        "hanging knee raise. In general keep this program to 7 "
                        "movements MAX"),
        ],
    ),
]


def _already_marked(session, date: str) -> bool:
    return (
        session.execute(
            select(Note).where(Note.kind == SESSION_KIND, Note.date == date)
        ).scalars().first()
        is not None
    )


def run(apply: bool) -> int:
    repo = WorkoutRepository()

    for planned in SESSIONS:
        with database.SessionLocal() as session:
            if _already_marked(session, planned.date):
                print(f"{planned.date}  already marked as a mobility session, skipping")
                continue
            existing = session.execute(
                select(Workout).where(Workout.date == planned.date)
            ).scalars().all()
            start_order = max((w.order or 0) for w in existing) if existing else 0

        movements = len({s.exercise for s in planned.sets})
        note = "" if not existing else f"  (appending after {len(existing)} existing rows)"
        print(
            f"{planned.date}  {len(planned.sets)} sets, {movements} movements{note}"
        )

        if not apply:
            continue

        # Performed, so completion is not in doubt. Noon local, matching the
        # marker note - `date` is a string prefix of the timestamp, and a
        # midnight-adjacent time is how sessions land on the wrong day.
        completed_at = datetime.fromisoformat(f"{planned.date}{NOON}")

        for offset, item in enumerate(planned.sets, start=1):
            repo.create(
                WorkoutCreate(
                    date=planned.date,
                    exercise=item.exercise,
                    category=item.category,
                    weight=item.weight,
                    reps=item.reps,
                    comment=item.comment,
                    order=start_order + offset,
                    completed_at=completed_at,
                )
            )

        with database.SessionLocal() as session:
            session.add(
                Note(
                    noted_at=f"{planned.date}{NOON}",
                    kind=SESSION_KIND,
                    body=planned.rationale + PROVENANCE,
                    # Neither 'manual' nor 'agent': nobody typed this into the
                    # app today and no model wrote it today. It was moved.
                    source="import",
                )
            )
            session.commit()

    if not apply:
        print("\nDry run. Re-run with --apply to write.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to the database")
    return run(parser.parse_args().apply)


if __name__ == "__main__":
    raise SystemExit(main())
