# Plans — current state

One row per plan. **This file is the entry point for a new session**: read it
before opening any individual plan, and update it when a plan's status changes.

The plans themselves hold the reasoning and the record of what actually
happened; this is only the index over them.

## Status vocabulary

Six values, used exactly. The `**Status:**` line at the top of each plan carries
the same word, so `grep -m1 '^\*\*Status:\*\*' docs/plans/0*.md` reproduces this
table.

| Value | Meaning |
|---|---|
| `Living` | Never "done" — a sequencing document that stays current |
| `Proposed` | Designed, not started |
| `In progress` | Partially landed; the plan says how far |
| `Implemented` | Done, with the revision it landed in |
| `Deferred` | Deliberately not being done now, with a reason |
| `Superseded` | Replaced by a later plan |

## The plans

| # | Plan | Status | Landed in | What's left |
|---|------|--------|-----------|-------------|
| 0001 | [Integration roadmap](0001-integration-roadmap.md) | Living | — | Refreshed 2026-08-09: the gap is closed except the deferred regrain |
| 0002 | [Schema foundation](0002-schema-foundation.md) | Implemented 2026-08-08 | `ac2fc3529985` | — |
| 0003 | [Units and metrics](0003-units-and-metrics.md) | Implemented 2026-08-08 | through `e96bd4b90873` | — (`body_composition` retired by 0010) |
| 0004 | [Workout session regrain](0004-workout-session-regrain.md) | **Deferred** | — | Deliberate. The highest-risk migration in the roadmap for the least benefit; §1 argues it should stay deferred |
| 0005 | [Food and notes](0005-food-and-notes.md) | Implemented 2026-08-09 | `12fed2487b4e` | Notes have an API but no UI — deliberate, see §7 |
| 0006 | [MCP server](0006-mcp-server.md) | Implemented 2026-08-09 | `backend/app/mcp/qs_mcp.py` | Shipping **read-only**. Enabling `QS_MCP_MODE=read-write` is built and tested but deliberately not done |
| 0007 | [Append-only audit log](0007-audit-log.md) | Implemented 2026-08-09 | `7e8f2b1ca79b` | §8's three open questions. The agent-facing read surface belongs to 0006 |
| 0008 | [BodySpec DEXA integration](0008-bodyspec-integration.md) | Implemented 2026-08-09 | through `70709fd96184` | — (`kcal_target` landed with 0005) |
| 0009 | [Drop AMRAP notation](0009-drop-amrap-notation.md) | Implemented 2026-08-08 | `fd709c41eb19` | — |
| 0010 | [Retire `body_composition`](0010-retire-body-composition.md) | Implemented 2026-08-09 | `86c8bbc9e2d7` | — |
| 0011 | [Supplement stacks](0011-supplement-stacks.md) | Implemented 2026-08-09 | `9ffbe9c21a0f` | — |
| 0012 | [Mobility](0012-mobility.md) | Implemented 2026-08-10 | `c4a92f18de07` | **Partly superseded by 0013** — §1, §3, §4's first mitigation, §9 and §10. Stale passages are marked in place; see the banner at the top of the plan |
| 0013 | [Mobility belongs to the set](0013-mobility-belongs-to-the-set.md) | Implemented 2026-08-19 | `d7e4f2a91b83` | Retires `exercises.is_mobility` and the day marker |
| 0014 | [Several mobility sessions](0014-several-mobility-sessions.md) | Implemented 2026-08-20 | `b6f31a90c4de` | Retires 0012 §2's "one rolling routine, not a queue" |
| 0015 | [The scale talks to the browser](0015-scale-over-web-bluetooth.md) | **In progress** | `f8a9cbb`, `00672bf` | Working on real hardware, desktop and Android. One question left (§10): whether several weighings between drains all arrive, or only the latest. §4 is revised — the scale sends undelivered readings, not its whole buffer |

## Where things stand

Every plan is landed except 0004, which is deferred on purpose, and 0015, which
works on real hardware but has one open question in §10. Two things are built, tested, and deliberately
**not switched on**: the general-purpose agent write tools
(`QS_MCP_MODE=read-write`) and a notes UI. Both are decisions, not
omissions — 0006 §8 and 0005 §7. Mobility's write tool is the one exception and
is argued in 0012 §5.

### Deliberately not switched on

Recorded here because they look like gaps and are decisions. `TODO.md` says so
too, but it is **gitignored** — this is the copy a fresh clone gets.

| Thing | Where it is argued |
|---|---|
| Agent **write** tools — `QS_MCP_MODE` defaults to `read-only`. **Two exceptions**: `write_next_mobility_session` (0012 §5) and `update_mobility_movement` (added 2026-08-13) are registered in both modes, so read-only means "the general-purpose write tools are absent", not "this process cannot write" | 0006 §8, 0012 §5, ADR-0004 amendments |
| Notes have an API and no UI | 0005 §7 |
| `v_blood_results` is not built — no data source | 0001 §5 |
| Plan 0004, the workout regrain | 0004 §1 |

### Verification debt

Work that is finished but under-checked. Not bugs; things nobody has looked at.

- **Only the Body section has been looked at in a browser.** Calendar,
  Progression and Exercises were glanced at; `/day/:date` (the 1,626-line
  WorkoutSession), `/upcoming` and the new `/mobility` have not been opened,
  and the first two are the most layout-heavy pages in the app. `/mobility` is
  mounted under test in both its states but has never been rendered in Chrome.
- **The mobility loop has never been run by a real MCP client.** It has been
  run end to end against a scratch copy of production by calling the tool
  functions directly — write, render, transfer, comment, read back, with the
  lifting program intact throughout. What is untested is an actual agent
  deciding *what* to prescribe from the Reads in `exercises.notes`.
- **Audit-log volume wants a check after a month of real use** (0007 §4).

Recently paid down:

- ~~The mobility program's history lives outside the database~~ — the four
  vault sessions are backfilled (0012 §9), 65 sets, with stated numbers carried
  verbatim and inferred ones named in each day's note. Loads nobody wrote down
  are NULL rather than guessed.

- ~~No supplement editor~~ — `/supplements` now has an "All supplements"
  catalog with an editor per entry, and `GET /api/food/{id}/usage` tells it how
  much history an edit would rewrite so the warning carries a real number.
  Renaming onto an existing `(name, brand)` was a 500; it is a 409 now.
- ~~Nobody has looked at the Food and Supplements pages~~ — done, and it found
  the biggest bug of the session: **Tailwind v4 was running v3 directives, so
  no variant generated any CSS and the desktop navigation had never rendered
  at any width.** Also two layout bugs on Supplements. Both pages are now
  mounted under test as well (`npm test`).
- ~~Nobody has looked at the app on a desktop~~ — a full audit at 402px, 768px,
  1024px and 1440px. Every page was a phone layout stretched to 1280px: a
  logged set put its name at x=115 and its delete button at x=1300, a month
  needed two screens, an exercise cost 155px. The pages that are one list now
  read in a 900px column and an entry is one line from 1024px. It also found
  **the food log's timezone bug** (below) and an install prompt that ignored
  "Not now" on every navigation.
- ~~No CI~~ — `.github/workflows/ci.yml` runs ruff, pytest, `alembic check`,
  a full `downgrade base` / `upgrade head` round trip, eslint, the jsdom tests
  and the build. **The round-trip step found a real bug on its first run**: the
  0011 downgrade rebuilt `food` while `v_daily_summary` still referenced it, so
  the rollback had never worked (0011 §7).
- ~~The MCP server is registered with no client~~ — `.mcp.json` at the repo
  root, project-scoped and read-only. Verified over real stdio JSON-RPC: four
  read tools visible, instructions delivered, and `UPDATE` through `query`
  refused by the engine.

**Commands, not numbers.** Everything below is derivable in a second and goes
stale the moment it is written down, so this section deliberately records how to
ask rather than the answer. A file asserting "177 tests pass" is wrong as soon
as someone adds a test, and worse than silence because it will be believed.

```bash
cd backend
.venv/bin/alembic current      # current revision
.venv/bin/alembic check        # drift between ORM and migrations
.venv/bin/pytest -q            # test suite
ruff check .                   # lint
git log --oneline -15          # what landed recently, and why
```

```bash
# the MCP server, read-only, against the real database
cd backend && QS_DB_PATH=../data/helf.db .venv/bin/python -m app.mcp.qs_mcp
```

```bash
# what the database actually holds, by instrument
sqlite3 data/helf.db "
  SELECT o.source, count(DISTINCT o.id) observations, count(m.id) metrics
  FROM observation o JOIN metric m ON m.observation_id = o.id
  GROUP BY o.source;"

# which quantities are defined vs actually recorded
sqlite3 data/helf.db "SELECT name, n_rows, first_seen, last_seen FROM v_metric_coverage ORDER BY n_rows DESC;"
```

## Things a cold session gets wrong

Each of these cost real debugging time at least once.

- **You cannot round-trip a migration on a copy of the database.**
  `migrations/alembic/env.py` resolves the URL from `settings.db_path` and
  ignores `sqlalchemy.url`, deliberately — it is wired to the application's own
  settings so a stray `alembic.ini` cannot point a migration somewhere
  unexpected. The cost is that `cfg.set_main_option("sqlalchemy.url", …)` is
  silently a no-op, so a "round trip on a scratch copy" runs **against
  production**, and the copy comes back untouched. That happened twice on
  2026-08-19 (`a1c8e5f30b64`, `e2b9c4d17a05`); no data was lost, but
  commit `9b1e8a8`'s message claims a round trip "on a copy of production"
  that was in fact on production. To exercise a migration off-line, point
  `DATA_DIR` (or `HELF_DB_PATH`, whatever `Settings` reads) at a scratch
  directory and check `alembic current` against the file you meant *before*
  trusting the result.
- **A CHECK added by `ALTER TABLE ... ADD COLUMN` is anonymous, and the ORM's
  is named — so `alembic check` reports drift forever.** Autogenerate compares
  constraints by name, so a `CheckConstraint(..., name="ck_x")` in
  `app/db/models.py` against an inline `CHECK (...)` in the database is a
  constraint to add that can never be added. It happened twice
  (`ck_exercises_rating`, `ck_upcoming_kind`), left the drift check red for
  nine days, and both are now fixed — by rebuilding the table, since SQLite
  cannot name a constraint in place. **Write `CONSTRAINT ck_x CHECK (...)` in
  the ADD COLUMN** and the rebuild is never needed. A permanently red drift
  check is worse than none: it trains everyone to ignore the one signal that
  catches the ORM and the schema diverging.
- **The pre-migration backup hook only sees what it can pattern-match.** It
  reads the Bash command text, so a migration driven through alembic's Python
  API used to slip past — `grep` is line-oriented and the matcher wanted
  `alembic` and the verb on one line. Fixed on 2026-08-19 and pinned by
  `backend/tests/test_pre_migration_hook.py`, which drives the real script with
  real payloads. Anything reaching alembic without naming it (a Makefile
  target, a shell alias) is still invisible to it — **back up by hand before
  anything unusual**.
- **Rebuilding a table with `batch_alter_table` drops inline unnamed CHECKs.**
  Batch mode rebuilds by *reflection*, which does not carry them across.
  `d7e4f2a91b83` silently dropped `ck_exercises_rating` that way on its first
  run — the constraint ADR-0002 calls the only rule both writers obey — and a
  test caught it. Both rebuilds now spell the DDL out.

- **The plans predate the schema.** 0008 was written against a `metric` table
  that had `source` and `observed_at` columns; 0003 moved both onto
  `observation` and dropped the `UNIQUE (observed_at, name, source)` constraint
  that 0008's idempotency design assumed. **Re-derive against the live schema
  before implementing any plan**, and when the data contradicts the plan, trust
  the data and fix the plan. 0008 §12 is the worked example.
- **`data/helf.db` is a live copy of production**, on local disk, bind-mounted
  into the container. WAL is on, so `cp` is not a consistent copy — use
  `sqlite3 … ".backup …"`. Back up before every migration.
- **Tests run the real migrations** (`conftest` does `upgrade head`), so new
  tables and seeds must arrive via a migration, not `create_all()`.
- **`from app.database import SessionLocal` at module scope binds the
  production engine.** It is only safe if `conftest`'s patch list happens to
  name that module. Reference `database.SessionLocal` through the module
  instead — a test that gets this wrong writes to `data/helf.db`, which has
  happened.
- **A SQLite trigger cannot read a `TEMP` table**, and an unqualified name in
  a trigger body binds to `main` when the trigger is compiled — a connection's
  temp shadow is never seen, silently. This killed Plan 0007 §3's actor design;
  §9 records what replaced it.
- **Three instruments write body composition** — `openscale`, `bodyspec`,
  `dexafit` — and they disagree by design. On 2026-03-10 the scale read 6.15
  percentage points of body fat above the DEXA scan. Never difference or
  average across `observation.source`.
- **A column added to an audited table is invisible to the log until its
  triggers are rebuilt.** They enumerate their columns into `json_object`, so
  the log keeps working and quietly stops recording the new field. Migration
  `b3d1c07a4e21` rebuilt the three `exercises` triggers when it added `rating`
  and `is_mobility`, and `d7e4f2a91b83` rebuilt them again when it dropped
  `is_mobility` and rebuilt the `workouts` pair to add it there — SQLite will
  not even drop a column a trigger names. Tests in `test_db_audit_log.py` fail
  if the next one forgets.
- **A CSS custom property declared in both the design-system block and the
  shadcn block silently loses.** `--border` was `#2a2a2d` in one and `0 0% 16%`
  in the other; the later won, so every `var(--border)` got a bare HSL triplet,
  which is not a colour, so the declaration was dropped — **no border rendered
  anywhere in the app**, in 42 places. Found by opening `/mobility` in Chrome,
  not by any test: nothing errors and the layout does not move. Shadcn-side
  names are suffixed `-tw` for this reason (`--accent-tw` already was;
  `--border-tw` since 2026-08-11).
- **`food_log.date` is `substr(consumed_at, 1, 10)`** — a string prefix, not a
  parsed instant. So the day an entry lands on is whatever the first ten
  characters spell, and `new Date().toISOString()` spells the *UTC* date. West
  of Greenwich every evening meal was filed under tomorrow: the POST returned
  201, the page refetched, and the entry was not there, because it was on the
  next day. Write local time. Guarded by a test in `Food.test.tsx`.

## Decisions that are settled

Recorded so they are not re-litigated. Full reasoning in `../decisions/`.

- **Pounds are canonical for body mass** (ADR-0003), units live in metric
  *names*, and no row carries a unit column.
- **The mobile nav bar is full at five items** (ADR-0006). A new destination is
  a tab beside an existing one, not a sixth entry.
- **SQLAlchemy for the app, raw SQL for the agent** (ADR-0002).
- **MCP over REST for agent access**, and read-only is not a confidentiality
  control (ADR-0004) — nothing secret goes in `helf.db`.
- **No AMRAP notation**; `reps` is an integer (ADR-0005).
