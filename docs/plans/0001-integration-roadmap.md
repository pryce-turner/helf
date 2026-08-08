# Plan 0001: Integration roadmap

**Status:** Proposed
**Prerequisites:** none — this is the entry point
**Related:** ADR-0002, ADR-0003, ADR-0004; `design/quantified-self-plan.md`

The design doc describes a target system as if built fresh. Helf already exists,
in production, with data in it. This plan is the bridge: what differs, in what
order to close the gap, and what can go wrong.

---

## 1. Where the two schemas disagree

### What exists (`backend/app/db/models.py`)

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

### Gap table

| Concern | Today | Target | Migration cost |
|---------|-------|--------|----------------|
| Workout grain | Flat. `workouts` row = one logged entry, ordered by `(date, order)`. No session entity | `workout` session parent → `exercise_set` children | **High** — see §4 |
| Body comp | Wide, 9 nullable columns (`db/models.py:105-124`) | Tall `metric` rows + `metric_def` | Medium — mechanical, reversible via view. **A single BodySpec DEXA scan carries 100+ scalars, which the wide table cannot hold at any price** |
| Units | Per-row `weight_unit`; training 9,292/9,292 lbs, scale labelled kg | lbs canonical for mass, no unit column | Low — training data untouched (ADR-0003) |
| `date` | Stored `String(10)`, set by the app | Generated `substr(ts,1,10)`, indexed | Low, but needs table rebuild |
| Food | Absent | `food` + `food_log` | **None** — purely additive |
| Notes | `workouts.comment` free text only | First-class `note` with `kind` + `source` — also the journal for unshaped data | Low — additive |
| `reps` | `String(16)`, for AMRAP notation never used in 9,252 rows | `Integer` | Low — verified lossless (ADR-0005) |
| Documents | Absent | `document` with `json_valid` check | None — additive |
| Views | None | `v_daily_summary`, `v_body_comp_daily`, `v_blood_results` | Low — additive, no data risk |
| Data access | SQLAlchemy + repositories | "No ORM" | **None** — scoping resolved in ADR-0002 |
| Agent surface | None | MCP server, 2 connections | Medium, mostly new code |
| Migrations | **None.** `create_all()` only | Required for all of the above | **Blocking** — see §3 |
| Pragmas | **None set.** FKs off, rollback journal | `foreign_keys=ON`, WAL | **Blocking** |
| Audit log | Absent | Absent from the design doc too | Additive (§7) |

---

## 2. Two findings that reorder the work

Both were discovered reading the code, and neither appears in the design doc.

### There is no migration framework

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

| Phase | Plan | Why here | Risk |
|-------|------|----------|------|
| 0 | 0002 | Nothing else is possible without it | Low |
| 1 | 0003 | Unit labels must be correct before any cross-domain query. Gated on verifying what openScale actually sends | Medium |
| 2 | 0009 | `reps` → integer. Small, lossless, and removes a silent-wrong-answer class before the agent can query. Cheapest while zero AMRAP rows exist | Low |
| 2 | 0005 | Purely additive, no migration, delivers the calorie tracking that motivated this — plus the journal for unshaped data | Low |
| 3 | 0007 | Wanted *before* the agent gets write access, not after | Low |
| 4 | 0008 | BodySpec DEXA import — needs `metric` (1) and `document` (2); supplies the RMR target that makes food tracking actionable | Medium |
| 5 | 0006 | Needs the schema and views from 1–4 to be worth querying | Medium |
| 6 | 0004 | High cost, low immediate value — see below | **High** |

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
| R2 | `foreign_keys=ON` surfaces existing orphans, app starts failing | High | Run the integrity check *before* enabling; fix or delete orphans as a data migration |
| R3 | Two processes contend on SQLite | High | WAL + `busy_timeout` in Phase 0, before the MCP server exists |
| R4 | Agent-authored SQL breaks silently after a schema change | Medium | `get_schema` tool reads live DDL; prefer views as a stable interface |
| R5 | Agent reads sensitive `note` rows | Medium | ADR-0004 — read-only ≠ confidential; restrict via views and `tools.include` |
| R6 | Regrain breaks reorder/drag-drop in a 1,626-line component | High | Deferred (Phase 5); adapter in MCP write path instead |
| R7 | `schema.sql` never recovered, DDL details lost | Medium | Reconstruct from the design doc's prose and `reference/qs_mcp.py`'s queries — every table it touches is inferable |
| R8 | Docker/stdio transport mismatch | Medium | Unresolved — decide transport in Plan 0006 before building |

### Backup, before any of this

The database is a single file. There is no reason not to copy it before each
migration:

```bash
cp "$HELF_DATA_PATH/helf.db" "$HELF_DATA_PATH/helf.db.bak-$(date +%Y%m%d-%H%M%S)"
```

This is the real mitigation for R1 and R2. Everything else is secondary.

---

## 5. What is deliberately not being done

- **Rewriting the backend to drop SQLAlchemy.** ADR-0002 — the design doc's "no
  ORM" is scoped to the agent's path.
- **Replacing the REST API.** It serves the PWA and is unaffected.
- **Blood work import** (`v_blood_results`). Still no data source. DEXA is no
  longer in this category — see `plans/0008-bodyspec-integration.md`.
- **The coaching loop** (design doc §6) — morning/evening/weekly prompts and the
  tone brief. **Dropped for now.** The focus is getting the data model right; a
  coaching layer built on a schema still in motion would have to be rebuilt
  anyway. The §6 text is preserved in `design/quantified-self-plan.md`.
  The *metrics* it needed — `alcohol_units`, `mood`, `sleep_hours` — **are**
  seeded, so the vocabulary and units are fixed before anything writes them
  (`plans/0003-units-and-metrics.md`). `v_metric_coverage` distinguishes
  "defined but never recorded" from "no change".
