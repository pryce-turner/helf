# Plan 0001: Integration roadmap

**Status:** Living — the sequencing document; see [README.md](README.md) for current state
**Prerequisites:** none — this is the entry point
**Related:** ADR-0002, ADR-0003, ADR-0004; `design/quantified-self-plan.md`

The design doc describes a target system as if built fresh. Helf already exists,
in production, with data in it. This plan is the bridge: what differs, in what
order to close the gap, and what can go wrong.

> **Refreshed 2026-08-09, and the gap is closed.** Every phase below has
> landed except the workout regrain, which stays deferred on purpose. The
> tables and risk register are kept rather than deleted — the reasoning is what
> was worth writing down, and a roadmap that erases its own history stops being
> checkable. Rows now carry where they ended up. [README.md](README.md) remains
> the per-plan status of record.

---

## 1. Where the two schemas disagree

### What existed when this was written

```
categories ──< exercises ──< workouts            (flat: one row per logged entry)
                        └──< upcoming_workouts
body_composition                                  (wide: one column per metric)
```

### What the design doc wants

```
exercise ──< exercise_set >── workout             (hierarchical: session → sets)
food ──< food_log
metric_def ──< metric                             (tall: one row per measurement)
document, note
```

### What exists now (`backend/app/db/models.py`)

```
categories ──< exercises ──< workouts            (still flat — 0004 deferred)
                        └──< upcoming_workouts
metric_def ──< metric >── observation             (tall; `observation` is the
                    └──── document                 act of measuring)
food ──< food_log
note
audit_actor, audit_log                            (mutation history, append-only)
```

`observation` is the one structure the design doc did not anticipate. A
"measurement" is several `metric` rows — a scale reports weight, fat, muscle
and water in one step off — and without a parent there is nothing to give a
stable id to and no way to say which instrument produced them. It is also what
made retiring the wide table possible (Plan 0003 §9, Plan 0010).

### Gap table

| Concern | When written | Where it landed |
|---------|--------------|-----------------|
| Workout grain | Flat. `workouts` row = one logged entry, ordered by `(date, order)`. No session entity | **Still flat, deliberately.** 0004 deferred; the MCP write path adapts a session-shaped tool onto flat rows (0004 §4, 0006 §8) |
| Body comp | Wide, 9 nullable columns | Tall `metric` + `observation` + `metric_def`. Table **dropped** in `86c8bbc9e2d7` (0010) after eight months of being written and never read |
| Units | Per-row `weight_unit`; training 9,292/9,292 lbs, scale labelled kg | Unit columns dropped (`e96bd4b90873`); units live in metric names (ADR-0003) |
| `date` | Stored `String(10)`, set by the app | Generated `substr(...,1,10)` STORED and indexed on `observation`, `food_log`, `note`. `workouts.date` is still app-set — it was never a timestamp to derive from |
| Food | Absent | `food` + `food_log` (`12fed2487b4e`), plus a page (ADR-0006) |
| Notes | `workouts.comment` free text only | `note` with `kind` + `source` (`12fed2487b4e`). API only — no UI, see 0005 §7 |
| `reps` | `String(16)`, for AMRAP notation never used in 9,252 rows | `Integer` (`fd709c41eb19`, ADR-0005) |
| Documents | Absent | `document` with the `json_valid` check (`61ccf127e583`), holding four DEXA payloads |
| Views | None | `v_daily_summary`, `v_body_comp_measurements`, `v_body_comp_daily`, `v_body_comp_series`, `v_metric_coverage`. **`v_blood_results` is not built** — still no data source |
| Data access | SQLAlchemy + repositories | Unchanged. ADR-0002 scoped "no ORM" to the agent's path |
| Agent surface | None | `backend/app/mcp/qs_mcp.py`, stdio, two connections, **read-only by default** (0006) |
| Migrations | **None.** `create_all()` only | Alembic; tests run `upgrade head` rather than `create_all()` (0002) |
| Pragmas | **None set.** FKs off, rollback journal | `foreign_keys=ON`, WAL, `busy_timeout` on both writers (0002, 0006) |
| Audit log | Absent | `audit_log`, trigger-populated and trigger-enforced append-only (`7e8f2b1ca79b`, 0007) |

---

## 2. Two findings that reorder the work

Both were discovered reading the code, and neither appears in the design doc.

### There is no migration framework

*(Both findings are fixed; kept because they are why the phase order is what it
is.)*

`backend/app/database.py:27-31` creates schema exclusively through
`Base.metadata.create_all(bind=engine)`. That function creates *missing* tables.
It never alters an existing one — it will not add a column, change a type, or
add a constraint to a table that is already there.

Every schema change in the design doc is therefore currently **unimplementable**
against a database that has data in it. This is not a nice-to-have; it is the
gate. Plan 0002 addresses it first.

### No pragmas are set anywhere

`create_engine` (`database.py:18-22`) passes only `check_same_thread` and
`pool_pre_ping`. A repository-wide search for `PRAGMA` returns nothing. Two
consequences:

- **Foreign keys are not enforced.** SQLite defaults `foreign_keys` to OFF. The
  FK definitions throughout `db/models.py` are, at runtime, documentation. There
  may already be orphaned rows.
- **The database is in rollback-journal mode**, which takes a database-level
  write lock. ADR-0002 and ADR-0004 both introduce a *second process* on this
  file. Without WAL, a `query` from the agent and a `POST /api/workouts` from
  the PWA will contend, producing `database is locked`.

Turning FK enforcement on may itself surface violations. That check runs before
anything else.

---

## 3. Phase order

Dependency-ordered. Each phase leaves the app working.

```
Phase 0 ── Schema foundation          plans/0002    BLOCKING
              │
              ├── Phase 1 ── Units + metrics       plans/0003
              │                 │
              │                 └── Phase 4 ── MCP server      plans/0006
              │                 │
              ├── Phase 2 ── Food + notes          plans/0005
              │
              ├── Phase 3 ── Audit log             plans/0007
              │
              └── Phase 5 ── Workout regrain       plans/0004    DEFERRED
```

| Phase | Plan | Why here | Risk | Landed |
|-------|------|----------|------|--------|
| 0 | 0002 | Nothing else is possible without it | Low | ✓ 08-08 |
| 1 | 0003 | Unit labels must be correct before any cross-domain query. Gated on verifying what openScale actually sends | Medium | ✓ 08-08 |
| 2 | 0009 | `reps` → integer. Small, lossless, and removes a silent-wrong-answer class before the agent can query. Cheapest while zero AMRAP rows exist | Low | ✓ 08-08 |
| 2 | 0005 | Purely additive, no migration, delivers the calorie tracking that motivated this — plus the journal for unshaped data | Low | ✓ 08-09 |
| 3 | 0007 | Wanted *before* the agent gets write access, not after | Low | ✓ 08-09 |
| 4 | 0008 | BodySpec DEXA import — needs `metric` (1) and `document` (2); supplies the RMR target that makes food tracking actionable | Medium | ✓ 08-09 |
| 5 | 0006 | Needs the schema and views from 1–4 to be worth querying | Medium | ✓ 08-09 |
| — | 0010 | Not foreseen here. Retiring the wide table is the tail of phase 1, and only became safe once the mirror had been exact for a while | Low | ✓ 08-09 |
| 6 | 0004 | High cost, low immediate value — see below | **High** | **Deferred** |

The order held. 0007 landing before 0006 is the one dependency that paid off
visibly: the MCP server's first concurrency run separated the API's writes from
the agent's in the audit log with nothing extra to build.

### Why food comes before the agent

Food is the one piece with no migration and no coupling: new tables, new
endpoints, new page. It's also the feature that prompted the design doc. It can
ship while the riskier phases are still being thought about, and it gives the
agent something to actually reason about when it arrives.

### Why the regrain is deferred

Plan 0004 sets this out in full. In short: it rewrites the schema's spine, and
the code most coupled to the current shape is
`frontend/src/pages/WorkoutSession.tsx` — at **1,626 lines**, by a wide margin
the largest file in the frontend, carrying drag-to-reorder, inline editing, and
set completion. The `PATCH /{id}/reorder` contract depends on the flat
`(date, order)` model directly.

Against that cost, the benefit is modelling purity. Every capability the design
doc actually asks for — daily summaries, cross-domain queries, agent logging —
can be delivered on the flat model with an adapter in the MCP write path. Do it
when there's a feature that needs it, not as a prerequisite.

---

## 4. Risk register

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| R1 | ~~Unit backfill halves all training weights~~ | **Retired** | ADR-0003 chose lbs; `workouts` is already 9,292/9,292 lbs and is no longer migrated at all |
| R1a | ~~Body-comp relabelled without checking the payload~~ | **Retired** | Measured: weight is kg (84.9–92.2, mean 88.4). `plans/0003` §1 |
| R1b | `muscle_mass` is a **percentage** (r = −0.985 vs weight), not a mass | **Confirmed real** | Seeds as `muscle_pct` and is never converted. Also a live display bug — `plans/0003` §2 |
| R2 | ~~`foreign_keys=ON` surfaces existing orphans~~ | **Retired** | The integrity check ran clean before enabling. Plan 0002 |
| R3 | ~~Two processes contend on SQLite~~ | **Retired** | WAL + `busy_timeout` on both. Measured: 25 API POSTs, 25 agent writes and 60 agent reads in parallel, zero errors (0006 §8) |
| R4 | Agent-authored SQL breaks silently after a schema change | Medium | **Live.** `get_schema` reads live DDL, and the server instructions push the model at the views. Unfixable in general — it is why the views exist |
| R5 | Agent reads sensitive `note` rows | Medium | **Live, and now real** — `note` exists and the agent can read it. ADR-0004: read-only is not confidentiality. Nothing secret goes in `helf.db` |
| R6 | Regrain breaks reorder/drag-drop in a 1,626-line component | High | Deferred (Phase 5); the adapter in the MCP write path shipped instead (0006 §8) |
| R7 | `schema.sql` never recovered, DDL details lost | Medium | **Retired by irrelevance.** The schema was rebuilt from the design doc's prose and is now defined by eleven Alembic revisions |
| R8 | ~~Docker/stdio transport mismatch~~ | **Retired** | stdio, with the server running on the host against the bind-mounted file. HTTP deliberately not built (0006 §1) |
| R9 | An audit log that was never tested for immutability | Medium | **Retired at birth.** The migration probes its own triggers and refuses to complete if an UPDATE or DELETE is permitted (0007 §9) |

### Backup, before any of this

The database is a single file. There is no reason not to copy it before each
migration — but **not with `cp`**. WAL has been on since Plan 0002, so the
`-wal` file holds committed pages the `.db` file does not, and a plain copy is
a torn one. This was written before WAL and was wrong from the moment 0002
landed:

```bash
sqlite3 "$HELF_DATA_PATH/helf.db" ".backup '$HELF_DATA_PATH/helf.db.bak-$(date +%Y%m%d-%H%M%S)'"
```

This is the real mitigation for everything above. Everything else is
secondary.

---

## 5. What is deliberately not being done

- **Rewriting the backend to drop SQLAlchemy.** ADR-0002 — the design doc's "no
  ORM" is scoped to the agent's path.
- **Replacing the REST API.** It serves the PWA and is unaffected.
- **Blood work import** (`v_blood_results`). Still no data source, so the view
  is not built — a view over nothing would tell the agent a series exists.
  DEXA is no longer in this category — see `plans/0008-bodyspec-integration.md`.
- **Agent writes.** Every write tool is built and tested, and
  `QS_MCP_MODE=read-write` turns them on. It is not turned on. That is a
  separate, deliberate act, and the audit log is what makes it a reversible
  one.
- **The coaching loop** (design doc §6) — morning/evening/weekly prompts and the
  tone brief. **Dropped for now.** The focus is getting the data model right; a
  coaching layer built on a schema still in motion would have to be rebuilt
  anyway. The §6 text is preserved in `design/quantified-self-plan.md`.
  The *metrics* it needed — `alcohol_units`, `mood`, `sleep_hours` — **are**
  seeded, so the vocabulary and units are fixed before anything writes them
  (`plans/0003-units-and-metrics.md`). `v_metric_coverage` distinguishes
  "defined but never recorded" from "no change".
