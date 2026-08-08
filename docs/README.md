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

### Design
- [Quantified-Self App — Architecture & Build Plan](design/quantified-self-plan.md) — the source design doc

### Plans
- [0001 — Integration roadmap](plans/0001-integration-roadmap.md) — gap analysis, phase order, risk register **(start here)**
- [0002 — Schema foundation](plans/0002-schema-foundation.md) — Alembic, pragmas, WAL — **Done**
- [0003 — Units and metrics](plans/0003-units-and-metrics.md) — kg normalization, wide→tall body comp
- [0004 — Workout session regrain](plans/0004-workout-session-regrain.md) — flat rows → session/set hierarchy
- [0005 — Food and notes](plans/0005-food-and-notes.md) — new tables, new surface
- [0006 — MCP server](plans/0006-mcp-server.md) — wiring `reference/qs_mcp.py` to the real DB
- [0007 — Audit log](plans/0007-audit-log.md) — append-only change history
- [0008 — BodySpec DEXA integration](plans/0008-bodyspec-integration.md) — API-sourced body composition
- [0009 — Drop AMRAP notation](plans/0009-drop-amrap-notation.md) — `reps` TEXT → INTEGER — **Done**

### Reference
- [`reference/qs_mcp.py`](reference/qs_mcp.py) — MCP server implementation from the design doc. **Not packaged or imported**; targets the design doc's schema, not the current one. Plan 0006 covers wiring it up.

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
