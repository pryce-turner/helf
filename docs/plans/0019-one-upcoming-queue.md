# 0019 — One upcoming queue

**Status:** Implemented 2026-11-21, migration `9c4e7b21f806`

Supersedes Plan 0012 §2's single-table decision (and with it the
"`kind`-scope every query" tax Plan 0014 kept paying). Plan 0017's movement
break and Plan 0018's set tiles are untouched.

## §1 What changed, and why the old shape was wrong

`upcoming_workouts.kind` split planned work into two programs — `lifting`
sessions generated from a Liftoscript script, `mobility` sessions written by
the agent — and the table carried a CHECK to prove it. The split encoded a
real difference in *authorship and presentation* as a difference in *kind of
thing*, and the price list was long:

- **Every query had to name its kind.** A missing filter did not error, it
  mixed the two: the Liftoscript generator's `delete_all` was one dropped
  predicate away from destroying the pending mobility session, and each
  repository method carried a `kind` parameter to defend against it.
- **Two session-number namespaces.** Lifting numbered from the generator,
  mobility from 1, and the collision never happened only because every query
  named its kind — see above.
- **Two transfer paths, two delete paths, two pages.** Lifting transfer
  renumbered from 1; mobility transfer appended after the day's work, flagged
  the sets, and promoted the rationale. The difference that mattered (the
  flag, the note) was per-set and per-session metadata, not a kind of row.

Meanwhile Plan 0013 had already established the right grain: mobility is a
property of the **set** — `workouts.is_mobility`, one boolean per logged set,
toggled by the day-view checkbox. The user's rule is now that every workout
has a mobility element, and the element is exactly the flagged sets. A queue
that sorts whole sessions into "mobility" and "not mobility" cannot say that;
a flag on each planned set can and does.

So: `upcoming_workouts.is_mobility`, one boolean per *planned* set, carrying
the same fact the logged set carries. Transfer copies it across; the day-view
checkbox adjusts from there. `kind` is gone.

## §2 What the queue looks like now

One table, one list, two authors — the difference between them is metadata,
not behaviour:

| | Liftoscript session | Agent session |
|---|---|---|
| Written by | `POST /liftoscript/generate` | MCP `write_next_mobility_session` (or `POST /api/mobility/pending`) |
| Metadata | none | `mobility_plan` row: `label`, `rationale`, `created_at` |
| `is_mobility` on rows | 0 unless asked | per item, default 1 |
| Lists on `/upcoming` as | `SESSION N`, every row | the label, rationale, folded routine |

- **`GET /api/upcoming/` returns the queue grouped by session** with the plan
  metadata joined in. A plan whose rows are gone is omitted, the rule the old
  mobility page followed.
- **Transfer is one path** (`POST /api/upcoming/session/{n}/transfer`):
  append after the day's existing work, carry each row's `is_mobility` onto
  the logged set, parse legacy `time` into `work_seconds`, and — when the
  session has a plan — promote its rationale into the dated
  `mobility_session` note `read_latest_mobility_session` reports back, then
  delete the plan. The response carries `label` when there was one.
- **Delete is one path** (`DELETE /api/upcoming/session/{n}`): rows and plan
  together, so a label cannot attach itself to a later session that reuses
  the number.
- **Generate really clears the board.** `delete_all` is unscoped and the
  route deletes the `mobility_plan` rows alongside. The protection the kind
  scope bought (a regenerate cannot silently destroy the agent's pending
  session) moves to the page: the confirm dialog counts the sets and **names
  the agent-written sessions it is about to wipe**. The user accepted this
  trade — "wipe everything, but warn before confirming."
- **Session numbers are one sequence.** A new agent session takes the global
  max + 1 over `upcoming_workouts` and `mobility_plan`; the generator clears
  both tables before renumbering from 1. A number never picks out two
  sessions, which is what transfer and delete being keyed by it requires.
  The migration renumbered the live mobility session 1 → 13 for exactly this.

## §3 What deliberately did not change

- **The mobility loop.** `read_latest_mobility_session` still reads the
  flagged sets of the most recent day that has any; `write_next_mobility_session`
  still writes under a label with a rationale and refuses per-set comments;
  `mobility_plan` keeps its name and shape. The loop's value was never the
  separate queue — it is the read-adjust-write cycle.
- **The day-view checkbox and `PATCH /date/{date}/mobility`.** The flag is
  still the user's to adjust on the day.
- **`POST /api/mobility/suggest`** (the movement-break shuffle) and the
  pool behind it.
- **Movement `form`/`application`, `rating`, the pool flag** — nothing about
  exercises is touched.

## §4 The per-item flag

`write_next_mobility_session` and `POST /api/mobility/pending` accept an
optional `mobility` boolean per item, **default true** — the writer is the
mobility loop, so everything it prescribes is mobility work unless an item
says otherwise. That is what "every workout has a mobility element" means in
the data: a session can prescribe a Romanian deadlift beside the pigeon squat
that is there to mobilise it, and each row keeps its own answer through
transfer. Liftoscript gained no syntax for this; a generated program is all
unflagged, and hand-flagging on the day view covers the rest.

## §5 Record of what happened

- Migration `9c4e7b21f806`: ADD `is_mobility` (named CHECK, per the
  cold-session note), backfill from `kind`, slide mobility sessions above the
  lifting max (production: 1 → 13, plan followed), DROP `kind`. Downgrade
  restores `kind` from the flag but does not renumber back — a round trip
  slides the number again (13 → 25), which is harmless and documented in the
  revision.
- **The migration reached production before its backup.** The dev server on
  :8000 runs with `--reload`, and writing the revision file restarted it;
  the lifespan's `init_db()` ran `alembic upgrade head` against the live
  database. The data landed correctly (verified counts and flags), and
  `data/helf.db.post-0019-one-queue.bak` was taken immediately after. The
  pre-migration hook that would have fired first lives in `.claude/` and
  does not exist in this environment — the lesson stands: with that server
  running, *writing* a migration file *is* migrating production.
- The mobility API shrank to `GET /last-session`, `POST /pending`,
  `POST /suggest`; pending/transfer/discard moved to the upcoming routes.
- `/mobility` 301s to `/upcoming` in both the backend SPA routes and React
  Router; the Training-section tabs are gone, and the Movement Break and
  Last Session cards live at the top and bottom of `/upcoming`.
- `alembic check` is green for this change. It still reports plan 0018's
  REAL-vs-Float drift on `workouts.actual_*_seconds` (b7e2 wrote REAL, the
  ORM says Float) — pre-existing, not this plan's, recorded here so the next
  reader does not think the merge caused it.
