# 0017 — Cardio

**Status:** Implemented 2026-11-01 · `a5f701728b12`

## 1. What was wrong

Every exercise was implicitly resistance work. A set was weight × reps, and the
logging form offered nothing else, so a Stairmaster session ("20 minutes, 60
floors") or a run ("32:15, 3.1 miles") had nowhere to go except a comment.
There was already a "Cardio" category colour in three pages, but no way to log
cardio.

## 2. The shape

**The exercise says it is cardio by carrying a unit.** `exercises.cardio_unit`
is nullable, and being non-null *is* what makes an exercise cardio. There is no
`is_cardio` beside it: a flag and a unit could disagree, and one column cannot.
The UI shows a switch, and switching it on makes a unit required.

**The set carries its own time, amount and unit.** `workouts.duration_s`,
`workouts.amount`, `workouts.amount_unit`. The unit is copied from the
exercise's `cardio_unit` when the set is logged, and can be changed there. That
is deliberate: if a run is re-labelled from miles to km later, the history
logged in miles keeps saying miles. The exercise's unit is only the default.

This is a per-row unit column, which ADR-0003 argues against **for mass**. Its
scope limit says it governs mass, and these are not one quantity in several
units. Floors, steps and miles are different quantities, so a single canonical
unit is not available. The CHECK keeps the vocabulary closed instead.

**Time is whole seconds** (`duration_s`), so it can be summed and charted. The
form takes `mm:ss`, `h:mm:ss` or a bare number of minutes. An unreadable entry
blocks the save rather than being dropped (`pattern` on the input).

**Units are a fixed vocabulary**: `miles`, `km`, `meters`, `floors`, `steps`,
`kcal`. A CHECK on both columns enforces it, since the agent writes raw SQL and
never passes through Pydantic (ADR-0002). `app/models/cardio.py` and
`frontend/src/lib/cardio.ts` are the two copies the HTTP side and the picker
use. **Adding a unit is a migration plus both copies.**

## 3. Why not the legacy columns

`workouts` already had `distance`, `distance_unit` and `time`, unused by the
UI. 0004 measured them on 2026-08-08 at 0 / 0 / 35 non-null rows. They were not
reused:

- `distance` would hold floors and steps, which are not distances.
- `time` is free text with 35 rows of unknown shape. Converting it to seconds
  needs someone to look at those rows first.
- `distance_unit` cannot gain a CHECK without rebuilding `workouts`. SQLite
  only accepts a constraint on an existing column through a rebuild, while a
  new column takes its CHECK in the `ADD COLUMN`, named, so `alembic check`
  stays clean.

**Still open:** drop `distance` and `distance_unit` (0004 §2 already says
"drop rather than migrate"), and decide what the 35 `time` rows become. Both
need the live database, which this change was not written against.

## 4. Out of scope

- **Upcoming / Liftoscript.** `upcoming_workouts` has no cardio fields, and a
  transferred session carries none. Planned cardio is a separate change.
- **Progression.** Its charts are estimated 1RM, which a cardio set has no
  inputs for. A cardio exercise still appears in its exercise list and charts
  as empty.
- **The MCP `log_workout` write tool** (read-write mode only, which is off)
  still writes weight × reps.

## 5. Verification

- `backend/tests/test_cardio.py`: create/edit semantics (omitted vs explicit
  null `cardio_unit`), set round trip, copy-to-date, 422 on an unknown unit or
  a negative duration, CHECKs refusing the raw writer, and both tables' audit
  triggers recording the new columns.
- Migration round trip on a scratch `DATA_DIR`: the pre-existing columns of
  `workouts` and `exercises` checksum identically before the upgrade, after it
  and after the downgrade. Audit triggers record the new shape at head and the
  old one after the downgrade, `integrity_check` is ok, `downgrade base &&
  upgrade head` succeeds, and `alembic check` is clean.
- Frontend: `lib/cardio.test.ts` (time parsing), `Exercises.test.tsx` (the
  switch, with the unit required), `WorkoutSession.test.tsx` (cardio fields
  replace weight/reps, the unit is prefilled, and the mobility toggle's full
  PUT keeps the cardio fields).
- Driven in Chromium against a scratch database at 402px and 1440px: created
  Stairmaster as cardio in floors, logged 20:00 / 60, edited to an invalid
  `20:75` (save blocked), then to `25:30`. The stored row is
  `duration_s=1530, amount=60, amount_unit='floors'` with weight and reps
  NULL.
- **Not run against `data/helf.db`.** The production copy was not available
  where this was written. The pre-migration hook takes the backup when it is
  applied.
