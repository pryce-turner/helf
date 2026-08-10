# Plan 0006: MCP server

**Status:** Implemented (2026-08-09) — `backend/app/mcp/qs_mcp.py`, shipping
**read-only**; see §8
**Prerequisites:** Plans 0002 ✓, 0003 ✓, 0005 ✓, 0007 ✓ (landed first, as
recommended)
**Related:** ADR-0002, ADR-0004

Wires `reference/qs_mcp.py` to the real database as a **client-agnostic MCP
server** — any MCP client can consume it. The file is already written and close
to complete; this plan covers the gap between it and Helf as deployed.

> **Scope revision.** An earlier draft targeted Hermes (NousResearch)
> specifically, per `design/quantified-self-plan.md` §3. **Hermes is out of
> scope.** No particular client is assumed. Two concrete changes follow: the
> config example below is standard MCP client JSON rather than Hermes YAML, and
> capability gating moves from client-side tool filtering into the server (§4),
> since no client feature can be relied on.

---

## 1. Transport: stdio

`reference/qs_mcp.py:295` ends with `mcp.run()` — stdio, the default MCP
transport and the one every client supports. The client launches the server as a
subprocess and speaks over stdin/stdout.

Two properties matter:

- **No authentication needed.** The server inherits the trust of whatever
  launched it. There is no listening socket and no network exposure.
- **Colocation required.** Client and server share a host and filesystem, so
  `QS_DB_PATH` must resolve on the machine running the client.

Helf runs in Docker with the data directory bind-mounted to the host
(`docker-compose.yml`: `${HELF_DATA_PATH}:/app/data`). The MCP server therefore
runs **on the host**, pointed at the host-side path — not inside the container.
It is a separate process that happens to open the same file (ADR-0002), so it
does not need to live where the API lives.

**HTTP transport is deliberately not built.** It would allow a remote client at
the cost of an authentication story that does not currently exist. Add it if
something genuinely needs to connect from another machine; until then it is
unjustified surface area.

---

## 2. Gap between `reference/qs_mcp.py` and this codebase

The file targets the design doc's schema. Against the schema these plans
actually produce, the deltas are:

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| G1 | `DB_PATH` defaults to `~/health/app.db` | `qs_mcp.py:33` | Point `QS_DB_PATH` at `settings.db_path`. Fail loudly if the file doesn't exist rather than letting SQLite create an empty one |
| G2 | `log_workout` assumes `workout`/`exercise_set` | `qs_mcp.py:250` | Plan 0004 is deferred → use the flat adapter in Plan 0004 §4 |
| G3 | `add_metric` warns on unknown metric name, inserts anyway | `qs_mcp.py:162` | Plan 0003 adds an FK to `metric_def`, so the insert now *fails*. Catch it and return a useful error listing valid names |
| G4 | `log_food` matches `brand IS ?` against a NULL-permitting UNIQUE | `qs_mcp.py:219` | Plan 0005 §1 recommends `''` for brandless; change to `= ?` |
| G5 | No `busy_timeout` on either connection | `qs_mcp.py:44-55` | Add `PRAGMA busy_timeout=5000` to both — this is what makes two processes coexist |
| G6 | `exercise` rows auto-created from agent input | `qs_mcp.py:271` | Silently creates "bench press", "Bench Press", "Benchpress" as three exercises. Match case-insensitively; return `exercises_created` so the agent can self-correct |
| G7 | `exercise.category_id` is `NOT NULL` | `db/models.py:36` | The auto-create at G6 doesn't supply one → FK violation once Plan 0002 enables enforcement. Needs an "Uncategorized" category |

G7 is the one that will actually break on first run. It is invisible today only
because foreign keys aren't enforced.

## 3. Packaging

`reference/qs_mcp.py` is deliberately *not* imported by the app (ADR-0002 — they
share a file, not a code path). Two options:

**A. Separate module in the backend package** — `backend/app/mcp/qs_mcp.py`,
run as `python -m app.mcp.qs_mcp`. Shares the venv and `settings` for the DB
path. Simple; slightly muddies the "no shared code path" boundary, though
importing only `config` is harmless.

**B. Standalone script** — `backend/mcp_server/qs_mcp.py` with its own minimal
deps (`mcp`, `pydantic`). Truest to ADR-0002; duplicates path configuration.

**Recommend A**, importing *only* `app.config.settings` and nothing else. The
boundary that matters is not importing repositories or ORM models.

Add the dependency as an extra so the API image doesn't carry it:

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.2.0"]
```

## 4. Client configuration and capability gating

### Standard MCP client config

Every MCP client uses substantially the same JSON shape (Claude Desktop, Claude
Code, Cursor, and others all read a `mcpServers` map):

```json
{
  "mcpServers": {
    "helf": {
      "command": "python",
      "args": ["-m", "app.mcp.qs_mcp"],
      "env": {
        "QS_DB_PATH": "/Users/pryceturner/Desktop/projects/helf/data/helf.db",
        "QS_MCP_MODE": "read-only"
      }
    }
  }
}
```

Nothing here is client-specific. A client with extra features (per-server tool
filtering, timeouts) may add its own keys, but the server must not depend on
them.

### Gating lives in the server

**`QS_MCP_MODE` is the control, and it is enforced by the server registering
fewer tools.** A client-side allowlist cannot be relied on when the client is
unknown — and a capability that only some clients honour is not a boundary.

```python
READ_ONLY = os.environ.get("QS_MCP_MODE", "read-only") != "read-write"

# read tools always registered: query, get_schema, daily_summary
if not READ_ONLY:
    mcp.tool()(add_metric)
    mcp.tool()(add_note)
    mcp.tool()(log_food)
    mcp.tool()(log_workout)
```

Two deliberate choices:

- **Default is read-only.** Forgetting to set the variable yields the safe mode,
  not the permissive one.
- **Unregistered, not refusing.** A tool that isn't registered is invisible to
  the model — it can't be attempted, argued with, or worked around. A tool that
  exists and returns "not permitted" invites retries.

This composes with, rather than replaces, the connection-level enforcement in
§5: even in `read-write` mode, `query` runs on the `mode=ro` connection.

**Start read-only.** Enable writes only after Plan 0007's audit log is in place
— once an agent can write, "did I log that or did the agent?" is unanswerable
without one.

## 5. Server instructions

Per the design doc §5, judgment the tools can't encode. With no client assumed,
this cannot live in client config — it ships **with the server**, via FastMCP's
`instructions` parameter, so every client receives it automatically:

```python
mcp = FastMCP("quantified-self", instructions=INSTRUCTIONS)
```

Keep the text in `docs/design/mcp-instructions.md` as the source of record and
load it at startup, so it's reviewable in git rather than buried in a string
literal. Contents:

- All masses are **pounds** (ADR-0003) — stored and displayed. BMI is kg/m² by
  definition, and lab markers keep their source units; `metric_def` is the
  authority, not assumption.
- Canonical metric names come from `metric_def` — query it rather than guessing.
- Prefer views (`v_daily_summary`, `v_body_comp_daily`) over raw tables.
- `reps` is an **integer** — compare and aggregate it normally. (Before Plan
  0009 it was TEXT carrying AMRAP notation, where `WHERE reps > 3` silently
  excluded `"10"`. ADR-0005 removed that hazard rather than documenting it.)
- **Query `v_metric_coverage`, not `metric_def`, to learn what data exists.**
  Some metrics are defined but not yet collected (`alcohol_units`, `mood`,
  `sleep_hours`); `n_rows = 0` distinguishes "never recorded" from "no change".
- Unshaped observations live in `note` and `document`, not in a formal table.
  `audit_log` is mutation history and is **not** a data source for questions
  about the body or training.
- A `workouts` row is one logged set, not a session (until Plan 0004).
- Body composition currently comes from BodySpec DEXA only (quarterly). The
  openScale daily series is parked, so do not assume a dense weight history.
- `metric` rows carry a `source`. Never mix sources in one series or average
  across them (`plans/0003-units-and-metrics.md` §4a).

The coaching tone brief (design doc §6) is **not** included — the coaching loop
is dropped while the data model settles.

## 6. Verification

```bash
QS_DB_PATH="$PWD/data/helf.db" python -m app.mcp.qs_mcp
```

The database lives at `data/helf.db` in the repository directory — the same file
the container bind-mounts, which is what makes the two-process contention in
ADR-0002 real rather than hypothetical. Hence WAL and `busy_timeout` (Plan 0002).

Then, with the app running to force concurrency:

1. `get_schema()` returns DDL including the views.
2. `query("SELECT * FROM v_daily_summary ORDER BY date DESC LIMIT 7")`.
3. `query("UPDATE workouts SET weight = 0")` → **must fail**. This is the
   ADR-0004 privilege boundary; if it succeeds, the read-only connection is
   misconfigured and nothing else about the security model holds.
4. `query("SELECT * FROM workouts")` on the full table → `truncated: true`,
   ≤1000 rows.
5. A deliberately slow query → times out at 5s, doesn't hang.
6. **Concurrency:** run a `query` while POSTing a workout from the PWA. Neither
   errors. Without WAL (Plan 0002) this is where `database is locked` appears.
7. `add_metric("nonexistent_metric", 1)` → clean error naming valid metrics
   (G3), not an opaque FK violation.

## 7. Rollback

Remove the `mcpServers` entry from the client's config. The server is a separate
process holding no state; stopping it affects nothing in the app. Reverting to
read-only is unsetting `QS_MCP_MODE` — the default.

## 8. What actually landed (2026-08-09)

`backend/app/mcp/qs_mcp.py`, packaging option **A** as recommended. All seven
gaps in §2 are closed; four of them turned out to be worse than the table said.

### The structure that made it testable

The tool functions are **plain functions with no decorators**, and the server
is assembled in `build_server()`. The whole write path is therefore exercisable
without an MCP client and without `mcp` installed — which matters because every
interesting failure here is in the SQL or the privilege boundary, not in the
protocol. 29 tests in `backend/tests/test_mcp_server.py`.

### G3 needed more than an error message

`add_metric` checks `metric_def` up front and returns the **valid vocabulary**
in the same response, rather than catching an FK violation. An agent that gets
"FOREIGN KEY constraint failed" retries; an agent that gets the list of legal
names fixes itself in one turn. `get_metric_names()` exists as a read tool for
the same reason and reads `v_metric_coverage`, not `metric_def`, so `n_rows =
0` distinguishes "never recorded" from "unchanged".

Idempotency had to be rebuilt, not adjusted: the reference upserts on
`UNIQUE (observed_at, name, source)`, which Plan 0003 deleted. It is now
find-or-create on `observation` (unique on `observed_at`, `source`) plus
`ON CONFLICT (observation_id, name)`. Two instruments reading at the same
instant stay two observations, which is the property that keeps a bioimpedance
estimate from overwriting a DEXA scan.

### G6 is worse than "three exercises"

`exercises.name` is UNIQUE, but SQLite's default collation is case-sensitive,
so the constraint would not have caught `bench press` either — the agent would
have created a second exercise, a second progression chart, and a silently
halved history. Matching is `COLLATE NOCASE`, and `exercises_created` comes
back in the response so a typo that has just become permanent is visible.

### An import that had to be deferred

`from app.config import settings` at module scope is unsafe here. A stdio
server is launched by a client with an arbitrary working directory, and
`Settings` reads a *relative* `.env` and **creates `../data` on import**. Run
from the repository root it dies parsing `CORS_ORIGINS=*`; run from elsewhere
it scatters empty data directories. The import is now inside
`_default_db_path()` and is reached only when `QS_DB_PATH` is unset.

### `FastMCP` is `MCPServer` now

mcp 2.0 renamed the class. Same `.tool()` and `.run()`. The dependency is
`mcp>=2.0.0`, as an extra so the API image does not carry it.

### Weights are pounds

`log_workout` takes `weight_lb`. Plan 0004 §4's adapter sketch says
`s.weight_kg`, which contradicts ADR-0003 and the data — `workouts` is
uniformly pounds. The adapter is otherwise as written: N flat rows sharing a
date, `order` continuing from whatever is already on that day rather than
restarting at 1 and colliding with the PWA's rows.

### Client configuration

```json
{
  "mcpServers": {
    "helf": {
      "command": "/Users/pryceturner/Desktop/projects/helf/backend/.venv/bin/python",
      "args": ["-m", "app.mcp.qs_mcp"],
      "cwd": "/Users/pryceturner/Desktop/projects/helf/backend",
      "env": {
        "QS_DB_PATH": "/Users/pryceturner/Desktop/projects/helf/data/helf.db",
        "QS_MCP_MODE": "read-only"
      }
    }
  }
}
```

`cwd` is not decoration — `python -m app.mcp.qs_mcp` needs `backend` on the
path.

### Verification

§6's list, run against `data/helf.db` with the app running:

| Check | Result |
|---|---|
| `get_schema()` includes the views | yes, 11,160 chars |
| `daily_summary` over a real week | 2026-07-08: 13 sets, 13,720 lb, target 2730 |
| `query("UPDATE workouts SET weight = 0")` | `attempt to write a readonly database` |
| `query("SELECT * FROM workouts")` | 1000 rows, `truncated: true` |
| runaway recursive CTE | `interrupted` after 5.0s |
| unknown metric name | clean error + the 18 valid names |
| tools registered in read-only mode | `daily_summary, get_metric_names, get_schema, query` — no writers |

**Concurrency**, against a `.backup` copy of production with uvicorn serving
it: 25 workout POSTs from the API, 25 `log_workout` calls and 60 `query` calls,
all in parallel. **Zero errors**, 50 rows landed, and the audit log separated
them correctly — the API's exercise auto-create recorded as `app`, the agent's
`add_metric` as `agent`. Without WAL and `busy_timeout` this is exactly where
`database is locked` appears.

### Still open

- **Writes are not enabled.** `QS_MCP_MODE` defaults to `read-only` and the
  documented config sets it explicitly. Everything needed to turn them on is
  built and tested; turning them on is a separate, deliberate act.
- The coaching tone brief (design doc §6) remains out, as §5 said.
