# Helf Documentation

Durable home for design docs, architecture decisions, and implementation plans.
Anything here is checked into git and survives the conversation that produced it.

## What goes where

| Directory | Holds | Lifecycle |
|-----------|-------|-----------|
| `decisions/` | Architecture Decision Records (ADRs) — one decision per file, numbered | **Immutable once accepted.** Superseded by a new ADR, never edited in place |
| `design/` | Design docs — the *what* and *why* of a system, before it exists | Living; edit as the design evolves |
| `plans/` | Implementation plans — the *how* and *in what order*, tied to real files | Living until executed, then marked Done |
| `reference/` | Standalone reference implementations and snippets not yet wired into the build | Frozen; illustrative only |

The split that matters: **a design doc argues for a shape, an ADR records the
commitment, a plan sequences the work.** When a plan reveals that a decision was
wrong, write a new ADR — don't quietly rewrite history.

## Conventions

- **Numbering** — `decisions/` and `plans/` use a zero-padded 4-digit prefix in
  creation order (`0003-short-slug.md`). Numbers are never reused or reordered.
- **ADR format** — Context / Decision / Consequences, plus a Status line
  (`Proposed`, `Accepted`, `Superseded by ADR-NNNN`). See
  [ADR-0001](decisions/0001-record-architecture-decisions.md).
- **Plan format** — every plan states its Status, its prerequisites, the files
  it touches, and an explicit rollback. A plan that can't say how to undo itself
  isn't finished.
- **Cite real paths.** Reference `backend/app/db/models.py:63`, not "the models
  file". Plans that don't name files rot silently.

## Index

### Decisions
- [ADR-0001](decisions/0001-record-architecture-decisions.md) — Record architecture decisions
- [ADR-0002](decisions/0002-sqlalchemy-for-app-raw-sql-for-agent.md) — Keep SQLAlchemy for the app, raw SQL for the agent
- [ADR-0003](decisions/0003-pounds-as-canonical-unit.md) — Pounds as the canonical unit for body mass
- [ADR-0004](decisions/0004-mcp-server-over-rest-for-agent-access.md) — Expose the DB to the agent over MCP, not REST
- [ADR-0005](decisions/0005-no-amrap-in-the-data-model.md) — No AMRAP notation in the data model; `reps` is an integer
- [ADR-0006](decisions/0006-food-is-a-tab-under-body-not-a-sixth-nav-item.md) — The mobile nav bar is full at five; a new destination is a tab, not an entry

### Design
- [Quantified-Self App — Architecture & Build Plan](design/quantified-self-plan.md) — the source design doc
- [MCP server instructions](design/mcp-instructions.md) — loaded verbatim at startup by the MCP server; the shortest orientation to the schema's conventions

### Plans

**[`plans/README.md`](plans/README.md) is the status of record** — read it
first. Status is deliberately not repeated here; it was, and the two copies
drifted.

- [0001 — Integration roadmap](plans/0001-integration-roadmap.md) — gap analysis, phase order, risk register
- [0002 — Schema foundation](plans/0002-schema-foundation.md) — Alembic, pragmas, WAL
- [0003 — Units and metrics](plans/0003-units-and-metrics.md) — kg normalization, wide→tall body comp
- [0004 — Workout session regrain](plans/0004-workout-session-regrain.md) — flat rows → session/set hierarchy
- [0005 — Food and notes](plans/0005-food-and-notes.md) — `food`, `food_log`, `note`, `v_daily_summary`
- [0006 — MCP server](plans/0006-mcp-server.md) — the agent's read path
- [0007 — Audit log](plans/0007-audit-log.md) — append-only change history
- [0008 — BodySpec DEXA integration](plans/0008-bodyspec-integration.md) — API-sourced body composition
- [0009 — Drop AMRAP notation](plans/0009-drop-amrap-notation.md) — `reps` TEXT → INTEGER
- [0010 — Retire `body_composition`](plans/0010-retire-body-composition.md) — the wide table, dropped
- [0011 — Supplement stacks](plans/0011-supplement-stacks.md) — preset groups of consumables, logged in one action

### Reference
- [`reference/qs_mcp.py`](reference/qs_mcp.py) — **Superseded.** The original MCP server from the design doc, kept as the record of what was designed. Its SQL does not match the database. The running server is `backend/app/mcp/qs_mcp.py`.

## Where the schema is described

Deliberately nowhere in prose, in one place. `AGENTS.md` says why: a written
schema goes stale and is then believed. In order of usefulness:

| Want | Look at |
|---|---|
| What each table is *for* | `backend/app/db/models.py` — every table carries a docstring, and `alembic check` fails if it drifts from the migrations |
| Why a table is shaped that way | The plan that created it — 0002 baseline, 0003 `metric`/`observation`/`metric_def`, 0005 `food`/`food_log`/`note`, 0007 `audit_log`, 0008 `document` |
| The authoritative current DDL | `sqlite3 data/helf.db .schema`, or `get_schema()` over MCP |
| The short orientation | [`design/mcp-instructions.md`](design/mcp-instructions.md) — written for an agent, and the fastest read for a person |

## Provenance

`design/quantified-self-plan.md` and `reference/qs_mcp.py` came from a
browser-based Claude conversation and were imported verbatim. The design doc
references a `schema.sql` that was never downloaded — see the open item in
`TODO.md`. UI/UX items come from Obsidian (`PryceVault/Lifting/Helf Notes.md`).

## Agent instructions

`CLAUDE.md` is now a one-line `@AGENTS.md` import; the substance lives in
`AGENTS.md` at the repo root. That file covers stack, structure, deployment, and
the design system — the previously-flagged gap (a design system spec stranded in
gitignored `.claude/`) is **resolved**, since the content moved inline.

Division of labour: `AGENTS.md` describes the system **as it is today**;
`docs/` argues about **how it should change**. Keep decisions and plans out of
`AGENTS.md`, and keep current-state reference out of `docs/plans/`.
