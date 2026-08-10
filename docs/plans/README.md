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
| 0001 | [Integration roadmap](0001-integration-roadmap.md) | Living | — | The sequencing argument. Its gap table predates 0002/0003/0008 landing |
| 0002 | [Schema foundation](0002-schema-foundation.md) | Implemented 2026-08-08 | `ac2fc3529985` | — |
| 0003 | [Units and metrics](0003-units-and-metrics.md) | Implemented 2026-08-08 | through `e96bd4b90873` | — (`body_composition` retired by 0010) |
| 0004 | [Workout session regrain](0004-workout-session-regrain.md) | **Deferred** | — | Deliberate. The highest-risk migration in the roadmap for the least benefit; §1 argues it should stay deferred |
| 0005 | [Food and notes](0005-food-and-notes.md) | Implemented 2026-08-09 | `12fed2487b4e` | Notes have an API but no UI — deliberate, see §7 |
| 0006 | [MCP server](0006-mcp-server.md) | Implemented 2026-08-09 | `backend/app/mcp/qs_mcp.py` | Shipping **read-only**. Enabling `QS_MCP_MODE=read-write` is built and tested but deliberately not done |
| 0007 | [Append-only audit log](0007-audit-log.md) | Implemented 2026-08-09 | `7e8f2b1ca79b` | §8's three open questions. The agent-facing read surface belongs to 0006 |
| 0008 | [BodySpec DEXA integration](0008-bodyspec-integration.md) | Implemented 2026-08-09 | through `70709fd96184` | — (`kcal_target` landed with 0005) |
| 0009 | [Drop AMRAP notation](0009-drop-amrap-notation.md) | Implemented 2026-08-08 | `fd709c41eb19` | — |
| 0010 | [Retire `body_composition`](0010-retire-body-composition.md) | Implemented 2026-08-09 | `86c8bbc9e2d7` | — |

## Where things stand

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
