"""Mobility-specific queries: the plan note, and the last session that was run.

`database.SessionLocal` is reached through the module deliberately - see the
header of `food_repo.py`.

**Why a `note` row is involved at all.** The prescription lives in
`upcoming_workouts` with `kind = 'mobility'`, the user's feedback lives in
`workouts.comment`, and which sets were mobility work lives in
`workouts.is_mobility`. One fact has nowhere else to go: **why this session
looks the way it does.** The agent's reasoning - what changed since last time
and what to watch for - is prose, dated, written by a model, which is precisely
what `note` is for.

It used to carry a second fact. The same row asserted *that* a day was a
mobility session, which meant unticking the day's checkbox deleted the
reasoning along with the assertion, because the two shared a row. Since
d7e4f2a91b83 the sets carry their own flag and the day is derived from them, so
this note asserts nothing: delete it and the session is still a mobility
session, with no recorded reason. That is the right failure - a missing
rationale is a gap in the record, not a change to what happened.

The kind still changes as the meaning does: `mobility_plan` while the session
is pending, `mobility_session` once it has been run, dated to the day it was
run on. At most one plan note exists at a time, because there is one rolling
routine. A session the user assembled by hand has no note at all, and that is
not an error - nothing prescribed it.
"""

from sqlalchemy import func, select

from app import database
from app.db.models import Exercise, MobilityPlan, Note, Workout
from app.utils.date_helpers import format_timestamp, get_current_datetime

#: Retired by b6f31a90c4de. Pending plans are rows in `mobility_plan` now,
#: because several can be alive at once and a note has no room for a name.
#: Kept only so a migration or an old export can still be recognised.
PLAN_KIND = "mobility_plan"
#: Run. Dated to the day it was logged on. Not a marker - the sets say
#: whether the day was mobility work; this only says why.
SESSION_KIND = "mobility_session"

#: Notes are dated by `substr(noted_at, 1, 10)`, so the time half only has to
#: be a valid-looking local timestamp that cannot drift across midnight.
NOON = "T12:00:00"


class MobilityRepository:
    """The plan note, and reading back the last session that was run."""

    @staticmethod
    def _serialize_note(note: Note) -> dict:
        return {
            "doc_id": note.id,
            "noted_at": note.noted_at,
            "date": note.date,
            "kind": note.kind,
            "body": note.body,
            "source": note.source,
        }

    @staticmethod
    def _serialize_plan(plan: MobilityPlan) -> dict:
        return {
            "session": plan.session,
            "label": plan.label,
            "rationale": plan.rationale,
            "generated_at": plan.created_at,
        }

    def get_plans(self) -> list[dict]:
        """Every pending mobility session, oldest first.

        Ordered by `session` rather than by creation time so the list does not
        reshuffle when one of them is revised — the page is a list you pick
        from, and a list that reorders under your thumb is a list you mis-tap.
        """
        with database.SessionLocal() as session:
            plans = session.execute(
                select(MobilityPlan).order_by(MobilityPlan.session.asc())
            ).scalars().all()
            return [self._serialize_plan(plan) for plan in plans]

    def get_plan_by_label(self, label: str) -> dict | None:
        with database.SessionLocal() as session:
            plan = session.execute(
                select(MobilityPlan).where(MobilityPlan.label == label)
            ).scalars().first()
            return self._serialize_plan(plan) if plan else None

    def get_plan(self, session_id: int) -> dict | None:
        with database.SessionLocal() as session:
            plan = session.get(MobilityPlan, session_id)
            return self._serialize_plan(plan) if plan else None

    def upsert_plan(self, label: str, rationale: str) -> dict:
        """Create a pending session under `label`, or replace the one that has it.

        **The label is the key.** Writing "Shoulder" twice revises the shoulder
        session and cannot touch "Low back" — which is the whole difference
        between this and the single rolling routine it replaces, where every
        write destroyed whatever was pending.

        Returns the plan including its `session`, which is what the caller
        writes the items against. A new session takes `max + 1` **within
        mobility**; lifting numbers its own sessions independently and the two
        never meet, because every query names its kind.
        """
        with database.SessionLocal() as session:
            plan = session.execute(
                select(MobilityPlan).where(MobilityPlan.label == label)
            ).scalars().first()

            if plan is None:
                highest = session.execute(
                    select(func.max(MobilityPlan.session))
                ).scalar()
                plan = MobilityPlan(
                    session=(highest or 0) + 1,
                    label=label,
                    rationale=rationale,
                    created_at=format_timestamp(get_current_datetime()),
                )
                session.add(plan)
            else:
                plan.rationale = rationale
                plan.created_at = format_timestamp(get_current_datetime())

            session.commit()
            session.refresh(plan)
            return self._serialize_plan(plan)

    def delete_plan(self, session_id: int) -> int:
        """Drop one pending session's metadata. The items are the caller's job."""
        with database.SessionLocal() as session:
            plan = session.get(MobilityPlan, session_id)
            if plan is None:
                return 0
            session.delete(plan)
            session.commit()
            return 1

    def record_session_note(self, session_id: int, date: str) -> dict | None:
        """Turn a pending plan's reasoning into the record of a session run.

        Called at transfer, the moment the session acquires a date. The plan
        row goes; what survives is a dated `note` carrying why the session was
        written, which is what `read_latest_mobility_session` reports back.

        Returns None if the plan has vanished — nothing to record, and an empty
        note dated to a day would be a row asserting nothing (0013).
        """
        with database.SessionLocal() as session:
            plan = session.get(MobilityPlan, session_id)
            if plan is None:
                return None

            note = Note(
                noted_at=f"{date}{NOON}",
                kind=SESSION_KIND,
                body=plan.rationale,
                source="agent",
            )
            session.add(note)
            session.delete(plan)
            session.commit()
            session.refresh(note)
            return self._serialize_note(note)

    def get_latest_logged(self, date: str | None = None) -> dict | None:
        """The last mobility session that reached the calendar, with its sets.

        With no `date`, **the day is derived**: the most recent date carrying
        any set with `is_mobility = 1`. Passing a date reads that day instead,
        which is how a session gets written from a specific one rather than
        from whatever happened last. Either way there is no marker to agree or
        disagree with the rows.

        A named date with **no flagged sets returns None**, rather than falling
        back to everything logged that day. The flag is the only thing that
        says a set was mobility work. A day the user assembled by
        hand is found the same way as one the agent prescribed, which is what
        the old marker needed a second writer to achieve.

        Returns **only the mobility sets** of that day. A mobility session run
        alongside lifting is one day's work in the calendar but not one
        session's work here, and the flag is what separates them - the same
        movement is a lift in one row and a loaded stretch in the next.

        Comments come back verbatim and unattributed beyond the set they hang
        off. They are the whole feedback channel (Plan 0012 §4). Note the cost
        of returning the mobility subset: a program-level remark left on a
        lifting set that day is not visible here.

        `rationale` is None when nothing prescribed the session - a day flagged
        by hand has sets but no note, and inventing prose for it would read as
        an instruction that was tried.
        """
        with database.SessionLocal() as session:
            if date is None:
                date = session.execute(
                    select(Workout.date)
                    .where(Workout.is_mobility.is_(True))
                    .order_by(Workout.date.desc())
                    .limit(1)
                ).scalars().first()
                if date is None:
                    return None
            elif not session.execute(
                select(Workout.id)
                .where(Workout.date == date, Workout.is_mobility.is_(True))
                .limit(1)
            ).scalars().first():
                # A named date with nothing flagged comes back empty rather
                # than falling back to the whole day. The flag is the only
                # thing that says a set was mobility work, and programming
                # from a day's lifting sets because they happened to be there
                # is worse than saying there is nothing to read.
                return None

            rows = session.execute(
                select(Workout, Exercise.name)
                .join(Exercise, Workout.exercise_id == Exercise.id)
                .where(Workout.date == date, Workout.is_mobility.is_(True))
                .order_by(Workout.order.asc(), Workout.id.asc())
            ).all()

            note = session.execute(
                select(Note)
                .where(Note.kind == SESSION_KIND, Note.date == date)
                .order_by(Note.noted_at.desc(), Note.id.desc())
            ).scalars().first()

            return {
                "date": date,
                "rationale": note.body if note and note.body else None,
                "sets": [
                    {
                        "exercise": name,
                        "weight": workout.weight,
                        "reps": workout.reps,
                        "time": workout.time,
                        "comment": workout.comment,
                        "order": workout.order,
                        "completed": workout.completed_at is not None,
                    }
                    for workout, name in rows
                ],
            }
