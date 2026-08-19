# 0013 — Mobility belongs to the set

**Status**: Implemented 2026-08-19 · migration `d7e4f2a91b83`

Supersedes plan 0012 §3 and §10, and retires `exercises.is_mobility` added by
`b3d1c07a4e21`.

## 1. The question both old flags got wrong

Two things called themselves mobility, and neither could answer what the loop
actually asks.

**`exercises.is_mobility`** marked a *movement* as mobility work. But a good
morning is a loaded hinge in one session and a loaded stretch in the next, and
one exercise row cannot hold both answers. 0012 §3 named the consequence
without drawing the conclusion: "a mobility routine borrows movements that are
also lifting movements — the good morning is in both — so *the last day
containing a mobility exercise* finds lifting days too." That is not a quirk of
the query. It is the flag being attached to the wrong thing.

**The day marker** — a `note` row of kind `mobility_session` — was the
workaround. It asserted "this day was a mobility session" because the rows
could not. It worked, and it cost three things:

- The marker and the agent's rationale were **one row**, so unticking the box
  deleted the reasoning. The UI needed a warning label for it (0012 §10), which
  is a design apologising for itself.
- It needed **two writers** — transfer, and a checkbox — because not every
  session comes from the planner. 0012 §9's backfill was that gap paid off
  retroactively over four days.
- It could not describe a **mixed day**. The real 2026-08-13 is two sets of
  rehab work opening a twelve-set shoulder day; the marker could only say the
  whole day was mobility or none of it was.

## 2. What replaced them

`workouts.is_mobility`, one boolean per logged set. Nothing else.

- **A mobility day is derived**: the most recent date carrying any flagged set.
  No marker to agree or disagree with the rows, so the class of bug where a
  stored flag contradicts the thing it describes cannot occur.
- **A mixed day works.** `read_latest_mobility_session()` returns the flagged
  sets, not the day, so a mobility session run alongside lifting is its own
  session.
- **One writer.** Transfer sets the flag from `upcoming_workouts.kind`, which
  already said `mobility`; the day view's per-set toggle sets it by hand. Both
  write the same field, so a hand-built session needs no second mechanism.
- **The rationale survives, demoted.** The `mobility_session` note is still
  written, now carrying only *why*. It asserts nothing: delete it and the
  session is still a mobility session with no recorded reason — a gap in the
  record rather than a change to what happened.

## 3. Decisions worth keeping

**The flag is sticky on update.** `WorkoutUpdate.is_mobility` defaults to
`False` and every other field on that model is a full replace, so a PUT that
only meant to change a comment would clear it. Editing a comment to add
feedback is *the* thing that happens to a mobility set after it is run — the
flag would vanish exactly when the loop depends on it. The repository therefore
writes it only when the key is present, told apart by `model_fields_set`, the
same way `ExerciseUpdate.rating` distinguishes omitted from null.

**The MCP gate moved from membership to history.** `update_mobility_movement`
had checked `exercises.is_mobility`. There is no such column now, so it checks
for at least one logged set with `is_mobility = 1`: a movement earns its place
by having been used that way. Still not a general exercise editor.

**`rating` stayed on the exercise.** It is an opinion *about the movement*, so
re-rating rewrites no history. `b3d1c07a4e21` put both columns in the same
place on that reasoning; it holds for one of them and not the other, and this
plan is the difference.

**The backfill maps movement to set.** Every set of a movement that carried the
old flag became a mobility set — the only mapping the schema supports. It is
exact where a movement was only ever mobility work and an over-count where it
was not, which is the same ambiguity that motivated the move, now visible per
set and correctable one tap at a time instead of being unanswerable.

## 4. What the migration had to be careful about

**Both tables' audit triggers were rebuilt.** They enumerate their columns into
`json_object`, so a new column is silently absent from the log until they are
recreated (0007 §AUDITED) and a dropped one leaves a trigger that will not
compile. SQLite also refuses to drop a column named in a trigger body, so the
`exercises` triggers came down first and went back up describing the new shape.

**`exercises` was rebuilt by hand, not by `batch_alter_table`.** SQLite will
not `DROP COLUMN` a column carrying a CHECK constraint, so a rebuild was
required either way — and alembic's batch mode rebuilds by *reflection*, which
loses an inline unnamed column CHECK. The first attempt silently dropped
`CHECK (rating IS NULL OR rating BETWEEN 1 AND 5)`, the constraint ADR-0002
calls the only rule both writers obey: the agent writes raw SQL and never
passes through Pydantic, so losing it means nothing bounds a rating at all. A
test caught it. Spelling the DDL out keeps every constraint visible in the
migration, and named the rating CHECK on the way past — which removed one of
the two standing `alembic check` drift cases.

## 5. Verification

`pytest` — 365 passed. One pre-existing failure remains,
`test_database.py::test_models_match_migrations`, reporting `ck_upcoming_kind`
as drift: declared named in the ORM, created anonymous by `c4a92f18de07`. It
predates this work and is unrelated to it; this plan halved it by naming
`ck_exercises_rating` during the rebuild above.

`npm test` — 46 passed, including 7 over the per-set toggle: its optimistic
state mid-flight, rollback on a failed write, that flagging one set of a mixed
day leaves the others alone, and that the PUT carries the rest of the set
unchanged. eslint and `tsc` clean.

Against the live database, at `d7e4f2a91b83`:

- 9,326 workout rows before and after; 2 flagged by the backfill, both
  `Lock 3` on 2026-08-13 — the rehab day that motivated this.
- Row counts identical to the backup across every table (`exercises` 179,
  `categories` 10, `workouts` 9,326, `metric` 600, `observation` 150).
- The `exercises` rebuild is content-preserving: `sha256` over
  `id|name|notes|rating|last_used|use_count` for all 179 rows is
  `d955c9af8efe…` in both the backup and the live database.
- `ck_exercises_rating` is named and still bites — `UPDATE exercises SET
  rating = 9` fails.
- `integrity_check` ok, `foreign_key_check` clean, all five audit triggers
  present, and `audit_workouts_update` now names `is_mobility`.

Backup `data/helf.db.pre-0013-mobility-flag.bak`, taken before any of it.

## 6. Settled: there is no day-level assertion, and none is wanted

Marking a whole day is gone and **is not coming back**. This is a decision, not
a gap waiting to be filled — recorded here because the absence otherwise reads
as an oversight and gets proposed again.

Nothing needs to assert that a day was a mobility day, because the sets already
say so. A stored day-level flag can only do one of two things: agree with the
rows, in which case it is redundant, or disagree with them, in which case it is
wrong and something has to decide which to believe. The old marker managed both
failure modes in eleven days — 0012 §9's backfill existed because days had sets
and no marker, and §10's checkbox existed because the marker needed a writer
the planner did not provide.

So: no marker note, no `is_mobility` on a day, no "session focus", no rehab or
deload day-type beside it. If a future session finds itself wanting to record
something about a day as a whole, that is a signal the fact belongs on the sets
— or that training needs a real session entity (plan 0004), which is a
different plan and not an excuse to reintroduce a marker in the meantime.
