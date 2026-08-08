# ADR-0002: Keep SQLAlchemy for the app, raw SQL for the agent

**Status:** Accepted
**Date:** 2026-08-07

## Context

`design/quantified-self-plan.md` §4 is titled "Data access layer: no ORM" and
argues:

> The query tool runs SQL the **LLM** wrote at runtime, so an ORM buys nothing on
> the read path — you'd bypass it and run raw SQL anyway.

Read as a whole-project directive, this conflicts head-on with what exists.
Helf's backend is built on SQLAlchemy 2.x with a repository layer that is a
meaningful fraction of the codebase:

| File | Lines |
|------|-------|
| `backend/app/repositories/workout_repo.py` | 307 |
| `backend/app/repositories/body_comp_repo.py` | 206 |
| `backend/app/repositories/upcoming_repo.py` | 204 |
| `backend/app/repositories/exercise_repo.py` | 168 |

Roughly 885 lines of working, tested data access, plus the ORM models in
`backend/app/db/models.py` and the session management in
`backend/app/database.py`. Ripping out SQLAlchemy would be a rewrite of the
entire backend with no user-visible benefit.

Re-reading §4 in context, its argument is scoped narrowly — it is about the
**MCP query path**, where the SQL is authored by a model at runtime. It says
nothing about the app's own fixed, hand-written CRUD.

## Decision

Treat "no ORM" as scoped to the agent's data access, not the application's.

- **The app keeps SQLAlchemy.** Repositories, ORM models, and session handling
  in `backend/app/` stay exactly as they are.
- **The MCP server uses stdlib `sqlite3` directly**, as
  `reference/qs_mcp.py` already does, with `row_factory = sqlite3.Row`.
- **The two share a database file, not a code path.** The MCP server does not
  import from `app.*` and does not go through the repositories.

The contract between them is the **schema**, plus the views (`v_daily_summary`,
`v_body_comp_daily`, `v_blood_results`) that the agent is steered toward.

## Consequences

- No backend rewrite. The §4 conflict was a scoping ambiguity, not a real
  incompatibility.
- **Two writers on one SQLite file.** This is the significant cost. It requires
  WAL mode and a `busy_timeout`, neither of which is currently set — see
  `plans/0002-schema-foundation.md`. Without WAL, the two processes will
  produce `database is locked` errors under concurrent access.
- Schema changes must be applied in one place (Alembic) and *observed* in two.
  A migration that renames a column silently breaks the agent's SQL, which is
  generated at runtime and therefore has no compile-time check. The
  `get_schema` tool mitigates this by letting the model re-read the live DDL.
- Business logic that must hold for both writers (unit validation, metric-name
  checks) has to live in the schema as `CHECK` constraints and foreign keys, not
  in Python — Python is only on one of the two paths. This is a genuine
  constraint on the design, and it pushes toward the stricter schema the design
  doc calls for.
- Some duplication is accepted: an insert may exist as both a repository method
  and an MCP write tool.
