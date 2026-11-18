# 0017 — Popcorn: equipment-free mobility, timed

**Status:** Implemented 2026-11-16, `5d1a7c3e8f02`

Popcorn is a movement snack: one equipment-free movement, held or repeated for
a timed interval, done in the office between tasks. 30 seconds on, a short
rest, 30 seconds on — a minute or two, no equipment, no change of clothes.

It is the interval timer doing the timing, and a shuffle button deciding what
to do. Three decisions were made with the user up front:

- **A finished run is logged automatically** as mobility sets on today's date.
- **One movement per shuffle**, with the times prepopulated and still
  adjustable — the shuffle picks the movement, not the prescription.
- **The pool is a new field on `exercises`**, not a list in the frontend and
  not a table of its own.

## 1. The pool is a column, and it is not the flag 0013 removed

`exercises.popcorn_seconds INTEGER NULL`. NULL is "not in the pool"; a number
is both membership and that movement's default interval.

The column is one field rather than a boolean plus a duration because the two
are never wanted apart: a movement is in the pool *as* a 30-second movement or
a 40-second one, and a boolean would need a second column to say which, free to
disagree with the first.

**This is not the `exercises.is_mobility` that `d7e4f2a91b83` dropped, and the
distinction is worth stating because the two look alike.** That flag claimed a
movement *was* mobility work, which is a fact about a performance and not about
the movement: a good morning is a loaded hinge in one session and a loaded
stretch in the next. Popcorn claims only that a movement **can be done with no
equipment for a timed bout** — a property of its setup, in the same family as
`form`. A bodyweight squat is in the pool and is still a lift, and nothing here
stops it being logged as one.

`docs/design/mcp-instructions.md:109` tells the agent there is "no mobility
flag on the exercise and no pool table", and that suitability is a judgement
made from `form` and `application`. That rule is about *suitability for an
objective* and it still holds — popcorn eligibility is not suitability, and an
agent prescribing a session reasons exactly as before. What the rule could not
anticipate is a consumer with no judgement: **a shuffle button cannot reason
from `form`, so it needs a pool to draw from.** The instructions file is
amended (§7) to say so rather than left to contradict a column the agent can
see.

Bounds: `CHECK (popcorn_seconds IS NULL OR popcorn_seconds BETWEEN 5 AND 600)`,
**named `ck_exercises_popcorn_seconds` in the ADD COLUMN itself**. An anonymous
CHECK from `ALTER TABLE` compares unequal to the ORM's named one and leaves
`alembic check` red forever — it happened twice (`ck_exercises_rating`,
`ck_upcoming_kind`) and cost nine days.

## 2. The seed, why it is mostly new movements, and why it is a script

The catalog is 194 rows and is a **gym** catalog: barbell, cable, machine.
Counting the equipment-free ones is quick and the answer is ten, which is not
a pool.

```sql
SELECT count(*) FROM exercises WHERE popcorn_seconds IS NOT NULL;   -- 28, seeded
```

The seed enpools those ten and inserts eighteen new movements with `form` text
and a default interval.

**It is `backend/migrations/seed_popcorn_pool.py`, run by hand — not part of
the migration.** The first version seeded from the migration and it broke five
existing tests: seeding a movement means filing it under a category, and the
migration had to create the categories it needed, so a freshly migrated
database acquired `Back`, `Shoulders` and `Arms` and the tests that assert on
the category list — and the audit tests that insert a category by name and
expect it not to exist — all failed. That is the same reason
`import_mobility_pool.py` is a script, and it says so in its own header:
*the tests migrate a temporary database from scratch, so a migration carrying
movement data injects all of it into every test run.* There is a second reason
here: every insert into `exercises` fires an audit trigger, so a
migration-seeded pool would write eighteen audit rows on every fresh install,
attributed to whoever happened to run the migration. Nothing in the read path
depends on the pool having members — unlike the `metric_def` vocabulary, which
is why *that* is seeded by migration.

`Crunch` and `Bicycle Crunch` are equipment-free and were left out: the pool is
not the ab catalog, and the philosophy is loaded stretching.

The `form` text is written to be **corrected, not trusted**: it is setup
cues in the voice of the existing rows, and it lives in the same field the
Exercises page edits, so a wrong cue is one edit from being right.
`application` is left NULL for all of them, which is the honest value —
nothing has been learned about these yet, and `e2b9c4d17a05`'s argument for
splitting the two fields is precisely that a guess in `application` is
indistinguishable from a lesson. `rating` is left NULL too: the protocol only
allows a rating from a direct statement of liking, and nobody has made one.

Idempotent, and **idempotent across a downgrade**: the inserts skip a name that
exists and the enpool only writes rows still NULL, so running it twice — or
after the user has curated the pool — changes nothing. It reports what it would
do until `--apply` is passed.

## 3. The timer: shuffle, then adjust

`IntervalTimer` gains a shuffle that draws one movement from the pool and sets
the times from it. The setting rows stay editable afterwards — the movement
and the times are separate things, and the user asked for the times to be
adjustable rather than imposed.

What a shuffle writes into the settings:

| Setting | From |
|---|---|
| `workSeconds` | the movement's `popcorn_seconds` |
| `restSeconds` | `min(30, max(10, work / 2))` — a rest that scales with the bout rather than a flat 15s for a 40s hold and a 40s hold alike |
| `exercises` | 2 |
| `rounds` | 1 |

and the movement's name and `form` are held in state beside the schedule, so
the run is *about* something rather than being anonymous work/rest.

**The shuffle is deliberately not uniform over the pool.** It takes three
candidates at random and picks the one with the oldest `last_used`, NULL
oldest of all. Uniform random gives the same movement twice in a row one time
in thirty, which for something done five times a day is several times a week;
three candidates and a tiebreak is six lines and makes a repeat rare without
being a rotation the user has to wait through.

The hero shows the movement during work, and the card under the controls keeps
the `form` text visible — the point at which a cue is useful is while the
interval is running, not before it starts.

**Adjusting a setting after a shuffle does not change the movement**, and the
run is logged as whatever was actually configured when it finished (§4), not
as the movement's default.

## 4. What a finished run writes

`POST /api/mobility/popcorn` takes `{exercise, date?, sets, seconds}` and
writes one `workouts` row per work interval:

- `is_mobility = 1` — the whole point, and what makes the day findable by the
  agent's next read (`d7e4f2a91b83`)
- `reps = NULL`, `time = '0:30'` — **a timed set has no rep count.** `reps` is
  an integer and is not a duration (ADR-0005); writing `reps = 1` for a 30
  second hold would put a rep in the progression series that never happened
- `completed_at` = now, so it lands already ticked
- `order` after everything already on the day, so several snacks in one
  afternoon stack in the order they were run

`time` is a free `String(32)` that nothing had written a format into. This
defines it as **`m:ss`** (`'0:30'`, `'1:00'`), which is what the timer
displays and what `formatClock` already produces.

Auto-log fires once, when the phase machine reaches `done`. Abandoning a run
with Reset writes nothing, which is the difference between "finished" and
"started". A failed POST is shown rather than swallowed — a session that
silently did not reach the log is worse than one that did not run.

**The set card had no `time` chip** (`WorkoutSession.tsx:747`), so a timed set
would have logged and then rendered as a bare exercise name with no data on
it — `time` has been in the schema since the baseline and is invisible
everywhere in the app. A chip is added next to the weight and reps ones.

## 5. `exercises.last_used` has been wrong for eleven months

Found while deriving the shuffle against the live database, and in scope
because the shuffle's tiebreak reads it.

`exercises.use_count` and `last_used` are maintained by
`ExerciseRepository.update_usage`, which **nothing calls**. The largest
`last_used` in the database is `2025-12-21` while `workouts` has rows through
today:

```
sqlite> SELECT max(last_used) FROM exercises;         -- 2025-12-21
sqlite> SELECT max(date) FROM workouts;               -- 2026-11-12
```

Two things downstream read it and are therefore wrong: the `/exercises` page's
usage counts, and `GET /api/exercises/recent`, which is what the day view's
"recent" list in the add form is built from — so **the exercises offered first
when logging a set are the ones last used in December 2025**.

Fixed by calling `update_usage` from `WorkoutRepository.create`, where the set
is written. It is an `UPDATE` on an audited table, so each logged set now also
writes an audit row for the exercise; that is correct rather than wasteful,
since a mutation with no trace is the thing 0007 exists to prevent, and §4 of
that plan already flags audit volume as wanting a check after real use.

## 6. Where it is found from

`/timer` was reachable only from a button on the day view — three taps from
opening the app, for something meant to be started between tasks.

The entry point is a **Popcorn card on the Mobility page**, which navigates to
`/timer?popcorn=1` and shuffles on arrival. It sits there because popcorn is
mobility work and that page is already where mobility is started from; the day
view's button stays.

A third tab on the Training section was considered and not taken: that
section's nav item is labelled **Upcoming**, and a Timer tab under it would sit
beneath the wrong heading. ADR-0006 is about a *new* destination needing a
home; `/timer` already has one.

## 7. Migration, triggers, and what the agent is told

`exercises` is audited, and the triggers enumerate their columns into
`json_object` — so a column added without rebuilding them keeps working and
quietly stops being recorded. `e2b9c4d17a05` is the template: drop the three
triggers, alter, recreate with the column list extended.

The migration is **only** the column, the CHECK and the triggers. The
movements arrive from the script in §2.

`docs/design/mcp-instructions.md` gains a short paragraph under the movement
entry, amending the "no pool table" line: `exercises.popcorn_seconds` names a
movement that can be done with no equipment for that many seconds, it is a
fact about the setup and **not** a judgement that the movement suits an
objective, which remains yours to make from `form` and `application`. The
instructions are the source of record for what the model is told, and a column
the model can see while being told there is no pool is a contradiction it will
resolve by trusting the schema.

## 8. Tests, and what they caught

- `test_db_audit_log.py` — `popcorn_seconds` appears in the exercises payload,
  in the same style as the rating test that catches a forgotten trigger
  rebuild; and the CHECK refuses 9 for the raw writer, the way the rating one
  does (ADR-0002: the agent's SQL never meets Pydantic).
- The pool endpoint returns only pooled movements and 404s nothing.
- `POST /api/mobility/popcorn` writes N sets, in order, all `is_mobility`,
  with `reps` NULL and `time` formatted; and it appends after what is already
  on the day rather than interleaving.
- `update_usage` from `create`: `last_used` and `use_count` move.
- `IntervalTimer.test.tsx` — shuffle loads a movement and the times; adjusting
  a time after a shuffle keeps the movement; a finished run posts exactly once;
  a failed post is visible and retryable.
- `alembic check` green, and a `downgrade base && upgrade head` round trip on
  a scratch `DATA_DIR` — which is what caught the empty-pool bug above.

Verified against production as well, not only the suite: 28 movements in the
pool, a run writing two sets with `reps` NULL and `time = '0:30'`, both
`is_mobility` and already completed, appended after the day's existing sets;
`last_used` and `use_count` moving on the movement that was run. The smoke-test
rows were deleted afterwards.

## 9a. What went wrong, and what it cost

Recorded because three of these are the kind of thing the next session repeats.

- **The first migration lost the pool on a downgrade/upgrade round trip.**
  It seeded the movements in the same migration that added the column, and
  the downgrade drops the column but leaves the rows — deleting seeded
  exercises would take anything logged against them. So a re-upgrade found
  every movement already present, inserted nothing, and the pool came back
  **empty** while the plan claimed idempotence. Found by running the round trip
  on a scratch `DATA_DIR`, which is the check the README asks for. Since the
  seed moved to a script it is moot for the movements, but the shape of the
  mistake is worth naming: *a migration that seeds a column it also drops is
  not reversible, and saying "idempotent" is not the same as checking.*

- **Seeding from the migration broke five tests**, via the categories it had to
  create. See §2.

- **The auto-shuffle's render-time state adjustment looped forever.** It
  compared `pool` against a `seenPool` state to run once, and `pool` is
  `undefined` while the query is in flight against a `null` initial value — so
  the guard was never equal and React hit its re-render limit. Both sides have
  to go through the same normalisation. It passed the type check and the
  single-file test run and only showed up in the full suite.

- **`waitFor` cannot be used in the timer's suite.** It waits on a timer, and
  that suite fakes timers, so it hangs until the test times out. The
  replacement flushes with several `act()` calls, each advancing the fake clock
  by 0ms — React needs a *tick* to commit an update under faked timers, not
  just a drained microtask queue.

- **`exercises.last_used` had no writer for eleven months** (§5), which is why
  the shuffle's "least recently used" tiebreak would have been reading fiction.

## 10. Deliberately not done

- **No per-session feedback field.** A comment on a mobility set is the user's
  and is the only feedback channel there is (0012 §4); popcorn writes none. If
  something is worth saying about a snack, it is said on the set afterwards in
  the day view, the same as any other set.
- **No pending popcorn session.** It is not prescribed in advance and is not
  the agent's to write; there is nothing for `mobility_plan` to hold.
- **`update_mobility_movement` gained no `popcorn_seconds` parameter.** The
  agent can already write the column through `query` in read-write mode, where
  the CHECK is the rule that binds it (ADR-0002), and the instructions are
  meant to stay short.
- **No circuit of several different movements.** One movement per run, per the
  decision above. The timer's existing exercises × rounds model is what makes
  "more than one" possible later without a schema change.
- **The shuffle does not know what was done today.** It reads `last_used`,
  which is a day's granularity; a movement run an hour ago is not excluded.
  Leaving it out keeps the rule to one clause, and a repeat within the day is
  a snack done twice rather than a fault.
