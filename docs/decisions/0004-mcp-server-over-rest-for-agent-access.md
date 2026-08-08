# ADR-0004: Expose the DB to the agent over MCP, not REST

**Status:** Accepted
**Date:** 2026-08-07

> **Scope revision.** An earlier draft framed this around Hermes
> (NousResearch) specifically, following `design/quantified-self-plan.md` §3.
> **Hermes is out of scope.** The target is a standards-compliant MCP server that
> any MCP client can consume — Claude Desktop, Claude Code, Cursor, or anything
> else speaking the protocol. The decision below is unchanged; only the client
> assumption is removed, and doing so strengthens the portability argument that
> motivated it.

## Context

Helf already has a complete REST API (`backend/app/api/`) covering workouts,
exercises, progression, upcoming workouts, and body composition. The obvious
move for LLM integration is to point the agent at the existing endpoints.

The design doc §3 argues against this: MCP tools are self-describing, so the
client discovers names and schemas automatically with no hand-written wrapper,
and the same server works across MCP clients — which is precisely the property
that matters once no particular client is assumed.

There is a second argument the design doc makes implicitly and that matters more
here. The REST API is shaped around **screens** — `GET /api/workouts?date=`,
`GET /api/progression/{exercise}` — because that's what the frontend needs. The
questions the agent needs to answer are not screen-shaped: *mood versus training
volume lagged two days*, *LDL across diet changes*. Serving those over REST means
either inventing an endpoint per question, or building a generic query endpoint —
at which point it's an MCP server with extra steps and no schema discovery.

## Decision

Expose the database to the agent as a **separate MCP server** process
(`reference/qs_mcp.py`), not through the existing REST API and not as a native
agent tool.

- **Read path:** one generic `query(sql)` tool over a read-only connection.
- **Write path:** typed, parameterized tools — no raw write SQL.
- **The privilege boundary is the connection, not the tool name.** Reads use
  `sqlite3.connect("file:...?mode=ro", uri=True)`; the engine itself refuses
  writes through that handle. String-inspecting SQL for `INSERT` is not a
  control — CTEs, pragmas, comments, and multi-statement all defeat it.
- The REST API stays exactly as it is, serving the PWA.

## Consequences

- The agent can answer cross-domain questions that were never designed for,
  without an endpoint per question.
- **Two processes, one SQLite file.** Requires WAL and `busy_timeout` — see
  ADR-0002 and `plans/0002-schema-foundation.md`.
- **Defense in depth is required, because a read-only connection is not a
  confidentiality control.** It stops writes, not reads: the agent can read every
  row in the database, including notes and body composition. Limiting *what* it
  can see is a separate concern from limiting what it can change, addressed by
  restricted views if it becomes one.
- **Capability gating belongs in the server, not the client.** A Hermes-specific
  design could lean on that client's per-server `tools.include` filtering. With
  no client assumed, the read-only/read-write split must be enforced by the
  server itself — it decides which tools to register — since no capability can be
  assumed of an arbitrary MCP client. This is a better boundary anyway: it holds
  no matter what connects.
- **Transport: stdio.** Universally supported by MCP clients and requires no
  authentication, because the client launches the server as a subprocess and it
  inherits that trust. The cost is colocation — server and client share a host
  and filesystem. HTTP transport would lift that at the price of building an
  auth story; not worth it until something actually needs to connect remotely.
- Guards are mandatory on the read path: single statement, row cap, statement
  timeout. Without them one `SELECT *` on a join dumps the database into the
  model's context.
- Schema changes are not caught at compile time on this path. The `get_schema`
  tool and the schema resource exist so the model can re-read live DDL.
