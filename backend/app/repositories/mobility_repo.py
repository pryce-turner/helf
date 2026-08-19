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

from sqlalchemy import select

from app import database
from app.db.models import Exercise, Note, Workout
from app.utils.date_helpers import format_timestamp, get_current_datetime

#: Pending. At most one, replaced wholesale each time the agent writes.
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

    def get_plan_note(self) -> dict | None:
        """The rationale for the session currently pending, if there is one."""
        with database.SessionLocal() as session:
            note = session.execute(
                select(Note)
                .where(Note.kind == PLAN_KIND)
                .order_by(Note.noted_at.desc())
            ).scalars().first()
            return self._serialize_note(note) if note else None

    def replace_plan_note(self, body: str, source: str = "agent") -> dict:
        """Write the pending session's rationale, replacing any previous one.

        Replace rather than append: a plan note describes the session that is
        pending, and only one session is ever pending. A superseded rationale
        left behind would be read as the current one by whichever query got
        there first.
        """
        with database.SessionLocal() as session:
            for stale in session.execute(
                select(Note).where(Note.kind == PLAN_KIND)
            ).scalars().all():
                session.delete(stale)

            created = Note(
                noted_at=format_timestamp(get_current_datetime()),
                kind=PLAN_KIND,
                body=body,
                source=source,
            )
            session.add(created)
            session.commit()
            session.refresh(created)
            return self._serialize_note(created)

    def promote_plan_note(self, date: str) -> dict | None:
        """Turn the pending plan into the record of a session that was run.

        Called at transfer, which is the moment the session acquires a date.
        The note keeps its body and its id - it is the same reasoning, now
        attached to the day it was actually applied on - and changes kind.

        Returns None when there was no plan note. It used to write an empty
        stand-in row here, because the read path keyed on the row's existence
        to decide whether the day happened. Nothing keys on it now - the sets
        carry that - so an empty note would be a row asserting nothing, dated
        to a day, waiting to be mistaken for a rationale.
        """
        with database.SessionLocal() as session:
            note = session.execute(
                select(Note)
                .where(Note.kind == PLAN_KIND)
                .order_by(Note.noted_at.desc())
            ).scalars().first()

            if note is None:
                return None

            note.kind = SESSION_KIND
            note.noted_at = f"{date}{NOON}"
            session.commit()
            session.refresh(note)
            return self._serialize_note(note)

    def get_latest_logged(self) -> dict | None:
        """The last mobility session that reached the calendar, with its sets.

        **The day is derived, not asserted.** The most recent date carrying any
        set with `is_mobility = 1` is the last mobility session; there is no
        marker to agree or disagree with the rows. A day the user assembled by
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
            date = session.execute(
                select(Workout.date)
                .where(Workout.is_mobility.is_(True))
                .order_by(Workout.date.desc())
                .limit(1)
            ).scalars().first()
            if date is None:
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
