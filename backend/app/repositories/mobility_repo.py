"""Mobility-specific queries: the plan note, and the last session that was run.

`database.SessionLocal` is reached through the module deliberately - see the
header of `food_repo.py`.

**Why a `note` row is involved at all.** The prescription itself lives in
`upcoming_workouts` with `kind = 'mobility'`, and the user's feedback lives in
`workouts.comment` on the logged sets - neither needs anything here. Two facts
have nowhere else to go:

1. **Which days were mobility days.** `exercises.is_mobility` cannot answer it.
   A mobility routine borrows movements that are also lifting movements - the
   good morning is in both - so "the last day containing a mobility exercise"
   finds lifting days too, and 2026-06-25 is exactly that: a pigeon squat and a
   calf raise logged beside a Romanian deadlift. The marker has to be written
   when the session is transferred, because that is the only moment anything
   knows the day was a mobility day.
2. **Why this session looks the way it does.** The agent's reasoning - what
   changed since last time and what to watch for - is the substance of the
   feature. It is prose, dated, written by a model, which is precisely what
   `note` is for.

One row carries both, and it changes kind as it changes meaning: `mobility_plan`
while the session is pending, `mobility_session` once it has been run, dated to
the day it was run on. At most one plan note exists at a time, because there is
one rolling routine.
"""

from sqlalchemy import select

from app import database
from app.db.models import Exercise, Note, Workout
from app.utils.date_helpers import format_timestamp, get_current_datetime

#: Pending. At most one, replaced wholesale each time the agent writes.
PLAN_KIND = "mobility_plan"
#: Run. Dated to the day it was logged on; this is the day marker.
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

    def promote_plan_note(self, date: str, fallback_body: str = "") -> dict:
        """Turn the pending plan into the record of a session that was run.

        Called at transfer, which is the moment the session acquires a date.
        The note keeps its body and its id - it is the same reasoning, now
        attached to the day it was actually applied on - and changes kind, so
        that "was this a mobility day?" has an answer for every past day.

        Writes a marker even when no rationale exists, because the marker is
        what the read path keys on. A session transferred with no plan note is
        a session the user built by hand, and it still happened.
        """
        with database.SessionLocal() as session:
            note = session.execute(
                select(Note)
                .where(Note.kind == PLAN_KIND)
                .order_by(Note.noted_at.desc())
            ).scalars().first()

            if note is None:
                note = Note(body=fallback_body, source="app", noted_at=f"{date}{NOON}")
                session.add(note)

            note.kind = SESSION_KIND
            note.noted_at = f"{date}{NOON}"
            session.commit()
            session.refresh(note)
            return self._serialize_note(note)

    def get_latest_logged(self) -> dict | None:
        """The last mobility session that reached the calendar, with its sets.

        Returns **every** set logged on that day, not only the ones whose
        exercise is flagged as mobility. The day is the unit: if a movement was
        performed during the session it is part of the session, and the flag is
        a property of the movement rather than of that performance.

        Comments come back verbatim and unattributed beyond the set they hang
        off. They are the whole feedback channel (Plan 0012 §4), and some of
        them are about the program rather than the movement - "keep this to 7
        movements max" was written against whichever set was on screen.
        """
        with database.SessionLocal() as session:
            note = session.execute(
                select(Note)
                .where(Note.kind == SESSION_KIND)
                .order_by(Note.noted_at.desc())
            ).scalars().first()
            if note is None:
                return None

            rows = session.execute(
                select(Workout, Exercise.name)
                .join(Exercise, Workout.exercise_id == Exercise.id)
                .where(Workout.date == note.date)
                .order_by(Workout.order.asc(), Workout.id.asc())
            ).all()

            return {
                "date": note.date,
                "rationale": note.body,
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
