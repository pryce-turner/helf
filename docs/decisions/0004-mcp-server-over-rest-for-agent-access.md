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

  **Amended 2026-08-10 (plan 0012 §5).** One write tool,
  `write_next_mobility_session`, is registered in *both* modes. So
  `QS_MCP_MODE=read-only` now means "the general-purpose write tools are
  absent", not "this process cannot write" — a real weakening of the mode as a
  summary, taken because the mobility loop's whole value is the agent writing
  the next session. The tool is scoped to planned rows for one session plus its
  rationale; it cannot log a workout, record a measurement, or alter anything
  already in the calendar.

  **Amended 2026-08-13.** A second tool, `update_mobility_movement`, joins it —
  same argument, applied to step 4 of the loop. The instructions told the agent
  to write down what a session taught it about a movement, and no tool existed
  to do it, so the one step that compounds was the one step no client could
  perform. It is scoped to `notes` and `rating` on a movement already
  performed as mobility work — at least one logged set with
  `is_mobility = 1`. It cannot invent that history, so a movement joins the
  loop's reach by being used that way: the user's judgement, expressed in
  the log rather than in a checkbox.

  **Amended 2026-08-19.** That gate used to read `exercises.is_mobility`.
  The flag moved to the set (plan 0013) because whether a movement is
  mobility work depends on the objective that day, and an exercise row
  cannot hold both answers. The scope is unchanged in substance: still not
  a general exercise editor.

  **This ADR's actual claim is unchanged**: the privilege boundary is the
  *connection*, not the tool name. `query` is opened `mode=ro` in either mode,
  so a model that talks its way into composing an UPDATE is still refused by
  SQLite itself.
- **Transport: stdio.** Universally supported by MCP clients and requires no
  authentication, because the client launches the server as a subprocess and it
  inherits that trust. The cost is colocation — server and client share a host
  and filesystem. HTTP transport would lift that at the price of building an
  auth story; not worth it until something actually needs to connect remotely.

  **Amended 2026-08-13.** Something does, and both halves of that sentence have
  since moved. `streamable-http` shipped, and is deployed as the `helf-mcp`
  compose service on `30172:8081` with `QS_MCP_HOST=0.0.0.0` — reachable across
  the tailnet, where `helf.pryce.fyi` resolves via AdGuard. stdio remains for
  clients that can spawn a process on the host; the two are not exclusive, and
  HTTP has the incidental benefit that one server process serves every client
  rather than each spawning its own writer on the file.

  **The auth story was considered and declined: the tailnet is the boundary.**
  There is no authentication anywhere in helf — not on this transport, not on
  the REST API, and CORS is `*`. This is a deliberate posture for a single-user
  system on a private network, not an omission, and it should not be
  "fixed" piecemeal by whoever next notices it.

  Three consequences worth stating plainly, because the deployment no longer
  makes them obvious:

  1. **Anything that can reach the port has the full registered tool surface**,
     including both `ALWAYS_TOOLS` writes. Read-only was never a
     confidentiality control and is now not a write control either.
  2. **`QS_MCP_MODE` is per-process, not per-caller.** One server cannot be
     read-only for one client and read-write for another. Differentiating them
     needs either a second process on a second port, or per-session tool grants
     in a client capable of them.
  3. **Which sessions get these tools is therefore the last remaining gate, and
     it lives in the client.** That inverts the reasoning above — gating was put
     in the server precisely because no client capability could be assumed. It
     holds for an arbitrary MCP client; it stops being the whole story once a
     general-purpose agent that also reads untrusted text is on the tailnet.
- Guards are mandatory on the read path: single statement, row cap, statement
  timeout. Without them one `SELECT *` on a join dumps the database into the
  model's context.
- Schema changes are not caught at compile time on this path. The `get_schema`
  tool and the schema resource exist so the model can re-read live DDL.
