# 0012 — Mobility: the loop the agent drives

**Status:** Implemented 2026-08-10 · **partly superseded 2026-08-19**
**Landed in:** `c4a92f18de07`, `backend/app/mcp/qs_mcp.py`, `/mobility`

> **Read this first.** [Plan 0013](0013-mobility-belongs-to-the-set.md)
> (`d7e4f2a91b83`) moved the mobility flag onto the *set*. Everything below
> that treats mobility as a property of a **movement** (`exercises.is_mobility`)
> or of a **day** (a `mobility_session` marker note) describes a shape that no
> longer exists. Affected: **§1** (the pool import), **§3** (the marker),
> **§4**'s first mitigation, **§9** (the backfill) and **§10** (the checkbox,
> withdrawn entirely). The stale passages are marked in place rather than
> deleted, because why they were wrong is the useful part.
>
> Still current: §2 (`upcoming_workouts.kind`), §4's core claim that set
> comments are the only feedback channel, §5 (the MCP write exception), §6
> (the page's two states), §7 and §8.

A rolling mobility routine that the agent adjusts one session at a time from
the user's own feedback. Unlike every other plan here, the interesting part is
not the schema — it is that a feedback loop which had been running in an
Obsidian vault for six weeks moves into the database, and what that costs.

## 1. What was already there, and why it moved

The program ran in `~/Documents/PryceVault/Lifting/Mobility/`: an `Overview.md`
per region holding the movement pool, and one dated note per session. Four
sessions existed — 2026-06-27, and then 08-06 through 08-08 daily. The loop the
vault's own `AGENTS.md` describes is exactly the one implemented here:

> Read the most recent session note's `## Notes` for feedback. Append any
> exercise-specific feedback to that exercise's entry in Overview. Generate the
> next dated session note with an adjusted routine.

It worked. What it could not do was reach the calendar. Only 2026-06-25 was
ever logged in helf, and that session was logged by hand; 08-06, 08-07 and
08-08 exist only as markdown. So the training history had a six-week hole in
it, the mobility work did not count toward the streak, and nothing in
`v_daily_summary` knew those days had happened.

**Decision: the vault's content moves into helf.** The movement pool becomes
`exercises` rows with `is_mobility = 1`, and each movement's markdown — *How to
perform* plus the *Application* section whose Reads are written as symptom →
cause → programming response — goes into `exercises.notes`.

> **Stale (0013).** There is no `is_mobility` on `exercises` and no pool table.
> The *notes* half of this decision stands and is the part that mattered; the
> flag half was the mistake. `import_mobility_pool.py` will not run as written.

`notes` is a single TEXT column, so the Reads are prose rather than queryable
rows. That was chosen over a structured `exercise_doc` table deliberately:
Overview is a *current-state document that gets rewritten*, which is exactly
what one editable markdown blob is, and the consumer is a language model that
reads prose natively. A structured version buys a query nobody has needed.

Imported by `backend/migrations/import_mobility_pool.py`, which parses
Overview.md rather than embedding a copy of it. 18 movements: 2 matched
existing exercises by name and were updated in place, 16 were created. Three
carried Enjoyment stars, which became `rating` 3, 4 and 5.

**The vault is not deleted.** The dated session notes are the history of how
this program was reasoned about and nothing in helf reproduces them. It stops
being written to; it stays readable.

## 2. Storage: `upcoming_workouts.kind`, not a second pair of tables

A pending mobility session is a list of prescribed sets waiting to be copied
onto a date. So is a pending lifting session. They differ in who writes them
and what the page looks like, not in shape — so `kind TEXT NOT NULL DEFAULT
'lifting' CHECK (kind IN ('lifting','mobility'))` and one table.

The alternative was `mobility_session` + `mobility_item` with a status, a
region, per-item `sets`/`per_side`/`block` columns and a `rationale`. It was
rejected as duplicating the exercise/category resolution, the transfer path and
the serialiser to gain columns that `comment` carries as prose. What it would
have bought — a session-level entity — is genuinely absent, and §3 is where
that bill comes due.

**Undated until transferred**, like upcoming lifting. A plan becomes dated at
the moment it is copied into `workouts`; before that, "when" is not a fact
about it.

**One session number.** Mobility rows always use `session = 1`
(`MOBILITY_SESSION`). There is one rolling routine, not a queue, so an ordinal
that counts up would be a number with nothing to say.

**Sets expand into rows.** `sets: 2, reps: 8` is two rows, not one row with a
`sets` column — because that is the grain the user logs at. The 08-08 feedback
reads "8 and then 10 reps on 30lb kb QL raise": two numbers, needing two rows
to land in. The page folds consecutive identical rows back into "2 x 8" for
display.

### The cost, stated plainly

**Every query on `upcoming_workouts` must now name its kind.** A missing filter
does not error — it silently mixes two programs. The two that would have hurt:

- `delete_all()` is the Liftoscript generator's clear-the-board step. Unscoped,
  generating a lifting program destroys the pending mobility session and the
  mobility tab falls back to "no session ready" for a reason nothing on screen
  explains.
- `get_by_exercise()` feeds the progression service's forward projection. A
  prescribed stretch at bodyweight is not a point on a 1RM curve.

Both are defaulted to `'lifting'` so existing callers keep their behaviour, and
both have a test whose name says what breaks.

## 3. What the single table cannot hold: a `note` row per session — superseded

> **Superseded 2026-08-19 by [plan 0013](0013-mobility-belongs-to-the-set.md).**
> Only one of the two facts below turned out to need a `note` row. "Which days
> were mobility days" is answered by `workouts.is_mobility` and the day is
> derived from the sets; there is no marker, and **none is to be reintroduced**
> ([0013 §6](0013-mobility-belongs-to-the-set.md#6-settled-there-is-no-day-level-assertion-and-none-is-wanted)).
> The rationale half stands: `note` still carries *why*, and only why.
> Kept as the record of why the marker looked necessary.

Two facts have no column, and both are load-bearing:

**Which days were mobility days.** `exercises.is_mobility` cannot answer this. A
mobility routine borrows movements that are also lifting movements — the good
morning is in both programs — so "the last day containing a mobility exercise"
finds lifting days too. 2026-06-25 in the live database is precisely that: a
weighted pigeon squat and a single-leg calf raise logged beside a Romanian
deadlift. Nothing about the rows says it, so something has to assert it —
transfer, at the moment a prescribed session acquires a date. **Amended
2026-08-15**: transfer is not the only such moment, because not every session
comes from the planner. See §10.

> **Superseded 2026-08-19 by [plan 0013](0013-mobility-belongs-to-the-set.md).**
> The premise above is wrong, and this section is kept only as the record of
> why. "The last day containing a mobility exercise finds lifting days too" is
> not a reason the rows cannot answer the question — it is the flag being on
> the movement instead of on the set. `workouts.is_mobility` says which sets
> were mobility work, the day is derived from them, and no marker is needed at
> all. Nothing in the current system reads a `mobility_session` note to decide
> whether a day happened.

**Why this session looks the way it does.** The agent's reasoning is the
substance of the feature; without it the tab is a list of stretches.

One `note` row carries both and changes kind as it changes meaning:
`mobility_plan` while pending, `mobility_session` once run and dated to the day
it was run on. ~~That is the day marker the read path keys on.~~ **Stale
(0013):** the read path keys on `workouts.is_mobility`. The note asserts
nothing now — carrying both facts in one row is exactly what made unticking the
old checkbox destroy the agent's reasoning.

This is a deliberate narrowing of §4's "feedback goes only in set comments" —
which governs the *user's* feedback. Agent-authored prose in `note` is what
`note` is for (0005 §1a), and `source` keeps the two apart.

## 4. Feedback: the existing per-set comment field, and nothing else

The user's feedback goes in `workouts.comment` on the logged sets, edited in
`/day/:date` where the field already exists. No new notes UI, no per-session
feedback box.

**The known cost.** Program-level feedback has no row of its own. The 08-08
session produced *"in general keep this program to 7 movements MAX"* — a rule
about the program, which under this design gets attached to whichever set was
on screen when it was thought of. Mitigations:

- ~~`read_latest_mobility_session()` returns **every** comment on the day, not
  just those on flagged movements, so nothing is dropped.~~ **Stale (0013):**
  it returns the day's *mobility-flagged sets* and their comments, so a
  program-level remark left on a lifting set that day is dropped. The tool
  description says so and tells the agent to `query` the whole day when a
  session reads as though feedback is missing.
- The tool description tells the agent that some comments describe the program
  rather than the movement they hang off.
- Standing program rules were moved into `docs/design/mcp-instructions.md`,
  where they are read every session instead of having to be rediscovered in an
  old comment. The seven-movement cap, core-first ordering, and static-stretch
  placement live there now.

## 5. MCP: a scoped write exception

Two tools, `read_latest_mobility_session` and `write_next_mobility_session`.
The read tool is an ordinary read tool. The write tool is registered in **both**
modes, via a new `ALWAYS_TOOLS` tuple.

This is a hole in 0006 §4's rule that the mode is the whole gate, and it is
worth naming what it costs: **`QS_MCP_MODE=read-only` no longer means the
process cannot write.** It means the general-purpose write tools are absent.

Why it was taken anyway: the mobility loop's entire value is the agent writing
the next session. A read-only mobility server can describe a session but not
produce one, which leaves the user copying a routine out of a chat window by
hand — the thing this replaces. The two remaining options were worse: flipping
the global mode switches on four unrelated write tools that were deliberately
left off (0006 §8), and leaving the default off means flipping an environment
variable before every session.

It is scoped as narrowly as the idea allows. The tool writes planned rows for
one session plus its rationale. It cannot log a workout, record a measurement,
or touch anything already in the calendar. **ADR-0004's actual claim is
untouched**: the privilege boundary is the connection, `query` is still
`mode=ro`, and no amount of argument gets a write through it.

`check_database()` gained a check for `upcoming_workouts.kind`, because the
write tool now exists in the default mode and would otherwise fail at first
call with "no such column" instead of at startup.

## 6. The page: two states, and no third

`/mobility`, a tab beside `/upcoming` under the Upcoming nav entry — the mobile
bar is full at five (ADR-0006), and this is the second time that decision has
paid for itself.

1. **A session is ready.** Rationale, the folded routine, a date picker
   defaulting to today, and a discard button.
2. **No session is ready.** What to do about it, plus the last session's
   comments — which is what makes the empty state actionable rather than a
   dead end.

`ready` is derived server-side from whether the pending session has items, not
stored, so there is no status column to fall out of step with the rows it
describes. There is no "generating" state: the agent writes the session in one
transaction, so from the page's point of view it either exists or does not.

## 7. Verification

```
349 backend tests, 40 frontend tests, ruff clean, eslint clean, tsc clean
alembic check          — no drift
downgrade/upgrade      — round trip, 30 lifting rows preserved
```

Against the live database, after the pool import — **a snapshot of 2026-08-10,
not a current description**. `exercises.is_mobility` was dropped by
`d7e4f2a91b83` (0013), and `Bosu Heel Toe` and the `Mobility` *category* were
deleted outright on 2026-08-19 along with their four sets from 2024-03-10:

```
exercises where is_mobility = 1 : 19   (18 imported + Bosu Heel Toe)
                        rated   : 3    (3, 4, 5 — matching the vault's stars)
                    notes bytes : 22,977
workouts                        : 9,292   (unchanged)
PRAGMA integrity_check          : ok
PRAGMA foreign_key_check        : (empty)
```

Backups: `data/helf.db.pre-mobility.bak` (before the migration),
`data/helf.db.pre-mobility-pool.bak` (before the import).

## 8. Open, and deliberately not done

- ~~The four vault sessions are not backfilled.~~ **Done 2026-08-11** —
  `backend/migrations/backfill_mobility_sessions.py`, 65 sets across 06-27,
  08-06, 08-07 and 08-08. See §9.
- **Region is not modelled.** The vault is structured by region and only "Lower
  Back" exists. A second region would need either a column or a naming
  convention; one region needs neither.
- **`rating` means enjoyment.** The vault is emphatic that enjoyment and value
  diverge and that the divergence is the useful signal. There is one rating
  column, so it holds enjoyment, and value stays in the notes. The ORM
  docstring predating this said "how good the movement is for this person" and
  has been corrected.
- **No per-side modelling.** "each side" is a cue in `comment`. Making it
  structured means deciding whether a two-sided set is one row or two, which
  changes what the logged history means; not worth it until something needs to
  count sides. It cost something in the backfill: 2026-08-08's "hit 8 on the
  left, failed on the right at 7" became two rows of 8 and 7, which is the
  right *shape* — two sets were performed — but the reader has to take the
  asymmetry from the comment rather than from the numbers.

## 9. The backfill (2026-08-11) — partly superseded

> **Stale (0013).** The mechanism described here is gone: the backfill's whole
> job was writing `mobility_session` **marker** notes, and there is no marker.
> Its *data* stands — the sets it wrote are still in the calendar — but they
> are found now by `workouts.is_mobility`, and the notes it left carry only the
> rationale. The three-tier provenance discipline below is the part worth
> keeping and is why this section is not deleted.
>
> Worth noticing in hindsight: this backfill existed because days had sets and
> no marker. That is the marker being the wrong mechanism, stated as a chore.

§8 argued against this and the argument was about invention, not about value.
Doing it anyway, with the invention labelled, is better than a six-week hole:
without it the first `read_latest_mobility_session()` returned `found: false`
and the program's whole history lived outside the database.

**Three tiers of number, kept distinguishable.**

| Tier | Rule | Example |
|---|---|---|
| **Stated** | The user wrote it down. Carried across with their words in the set's `comment` | "8 and then 10 reps on 30lb kb QL raise" |
| **Prescribed** | The routine said 2x8 and nothing was said afterwards | Hanging knee raise on 08-08 |
| **Inferred** | Reconstructed from elsewhere, and named in the note | bar-only good morning = 45lb |

The prescribed tier is safe because **the session notes are a list of
deviations**. A movement under "Held unchanged" with no feedback went to plan;
that is what the vault's own workflow means by holding it unchanged.

Only two inferences were needed, and 2026-08-08 confirms both: a bar-only good
morning is 45lb and "+15lb plates" is 75lb (its stated "75lb x 6 reps x 2
sets"), and the QL kettlebell prescribed as "~25-30lb" is 30lb (its stated
"30lb kb QL raise").

**A load never written down is NULL, not a guess.** An invented weight becomes
a point on a progression chart and the baseline the next session is programmed
against — strictly worse than a gap. So the unweighted pigeon regressions and
every calf raise load before 08-08 are NULL.

Each day carries its `mobility_session` ~~marker~~ note with the vault's
rationale plus a provenance paragraph stating it was backfilled and which
numbers were inferred. `source = 'import'`: nobody typed it into the app today
and no model wrote it today — it was moved. **Stale (0013):** that note no
longer marks anything; the sets do.

**2026-06-25 was left alone.** It is already in the calendar with mobility
movements on it — a pigeon squat and a single-leg calf raise beside a Romanian
deadlift — and it is not one of the vault's sessions; the earliest of those is
06-27, whose rationale is that the RDL is *being replaced*. ~~It is not marked
as a mobility day, so~~ **(0013)** none of its sets are flagged, so
`read_latest_mobility_session()` will never return it — the conclusion survives
the mechanism it was argued from.

Verification: 9,292 → 9,357 workout rows, 4 `mobility_session` notes, a re-run
is a clean no-op. Backup `data/helf.db.pre-mobility-backfill.bak`.

## 10. Marking a day by hand (2026-08-15) — superseded

> **Superseded 2026-08-19 by [plan 0013](0013-mobility-belongs-to-the-set.md),
> migration `d7e4f2a91b83`.** The day-level marker, its two endpoints
> (`GET`/`PUT /api/mobility/day/{date}`) and the `Mobility session` checkbox
> are all gone. Mobility is a property of the set now, and a mobility day is
> derived from the sets rather than asserted beside them. This section stands
> as the record of a design that worked and was still wrong — in particular
> the third bullet below, which apologises for the marker and the rationale
> sharing a row, is the tell that the marker was in the wrong place.
>
> **Do not build on anything in this section, and do not reintroduce a
> day-level marker in any form.** That is settled — see
> [0013 §6](0013-mobility-belongs-to-the-set.md#6-settled-there-is-no-day-level-assertion-and-none-is-wanted).

§3 said only transfer knows a day is a mobility day. That was true of sessions
the planner produced and false of every other kind, and the gap has a cost that
compounds: `read_latest_mobility_session()` reads the **last marked day**, so a
session run without going through `/mobility` — built by hand in the day view,
or run away from the app and logged afterwards — leaves the agent writing the
next prescription from a session that is no longer the last one. The backfill
(§9) was this same hole paid off retroactively, one script, four days.

**The fix is a checkbox on `/day/:date`**, `Mobility session`, backed by
`GET`/`PUT /api/mobility/day/{date}`. It writes the same `mobility_session`
marker that transfer promotes. No new table, no new kind, no flag on the day.

Four decisions worth keeping:

- **PUT, not POST plus DELETE.** The caller knows the state it wants, not the
  transition. Idempotent in both directions, so a double tap on a phone means
  what one tap meant.
- **Re-marking never rewrites the body.** The marker and the agent's reasoning
  are one row (§3). A day already marked by transfer carries the rationale in
  that body; a checkbox that says *whether* must not overwrite *why*.
- **A hand-marked day gets an empty body, not a stand-in sentence.** The agent
  reads that field as what the session was written to achieve. Nothing was
  prescribed, and an invented rationale would be read as one that was tried.
  Same reasoning as §9's "a load never written down is NULL, not a guess".
- **An empty day cannot be marked.** The control is disabled until something is
  logged, because the marker's whole function is to point the agent at a day's
  sets, and a day with none is a worse input than no day at all. It stays
  enabled while marked, so a day emptied afterwards can still be corrected.

**The date is pattern-checked in the path.** `note.date` is `substr(noted_at,
1, 10)` computed, so nothing downstream rejects a malformed one — it becomes a
marker dated to nonsense, and `ORDER BY noted_at DESC` sorts nonsense above
every real date, which would hand the agent that row as the last session
performed for good. A regex in the path costs nothing and closes it.

**Unchecking deletes the row**, rationale included, since the two facts share
it. Recoverable from `audit_log` (0007) and not from the UI, so the control
says so when there is something to lose.

Verification: `pytest tests/test_api_mobility.py` — 21 passing, including that
marking a transferred day leaves its rationale intact, that unmarking hands the
agent the previous marked day, and that a malformed date is a 422 with `note`
still empty. `npm test` mounts the day view: 7 cases over the toggle, including
the optimistic state mid-flight and its rollback on a failed write. No
migration, so no backup — this adds no schema.
