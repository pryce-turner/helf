# Quantified-Self App — Architecture & Build Plan

A personal workout/health tracker backed by SQLite, exposed to a chat agent
(Hermes, by NousResearch) through a small MCP server. Goal: hold heterogeneous data
(training, body composition, blood work, food, mood) and let an LLM reason
across all of it holistically.

Full DDL lives in `schema.sql` — this document is the surrounding plan.

---

## 1. Data store: SQLite

Keep SQLite. At personal scale (one user, years of daily data = tens of
thousands of rows) you never hit a capacity or performance wall. The earlier
TinyDB slowness came from loading and rewriting the whole JSON on every
operation with no indexing — SQLite fixes exactly that: one file, but with
B-tree indexes so a query touches only relevant pages.

**Revisit only if the access pattern changes, not because of data volume:**
- Remote / multi-device continuous access → libSQL/Turso (keeps SQLite
  semantics, adds a server) or Postgres.
- Semantic search over notes becomes central → `sqlite-vec` is likely enough;
  Postgres + `pgvector` if it grows.

Pragmas: `foreign_keys = ON`, `journal_mode = WAL`.

---

## 2. Schema design (see `schema.sql`)

Three shapes, each for a different job, all joined at day grain:

- **Relational** where the data is genuinely relational:
  `exercise` → `workout` → `exercise_set`, and `food` → `food_log`.
- **One tall `metric` table** for the open-ended scalar stream — body weight,
  DEXA-derived body comp, blood markers, subjective ratings. New measurement =
  new rows, never a migration. `metric_def` holds units + reference ranges
  (drives out-of-range flagging).
- **`document`** keeps each raw import (DEXA/lab JSON) whole, with a
  `json_valid` check; the handful of scalars you care about are *promoted* into
  `metric` with a `document_id` back-reference for provenance.
- **`note`** for free text (journal, injuries, workout notes).

**Conventions baked in:**
- Every time-stamped table has a generated, indexed `date` column
  (`substr(ts, 1, 10)`). That's the universal join key — no separate "day"
  spine table; the spine emerges from a `UNION` of dates in `v_daily_summary`.
- **All weights/masses in kg.** Reconcile units on import — never mix units in
  `metric.value`. This is the one real footgun of a tall table.

**Views (the ergonomic + LLM-facing layer):**
- `v_daily_summary` — one holistic row per day (training volume, kcal, body
  weight, mood). The single most useful object to hand the LLM.
- `v_body_comp_daily` — tall `metric` pivoted into friendly columns.
- `v_blood_results` — blood metrics joined to `metric_def` with an
  in/out-of-range flag.

---

## 3. LLM integration: an MCP server, not a REST endpoint

Hermes speaks MCP natively — it's had a built-in MCP client since v0.2.0. At
startup it discovers each configured server and registers its tools into the
normal tool registry, so they appear alongside built-in tools like `terminal`
and `read_file`. DB access belongs here, as an MCP server, not as a native
Hermes tool or a REST endpoint.

Why MCP over a raw REST endpoint: MCP tools are self-describing — Hermes
discovers tool names and schemas automatically, no hand-written wrapper or
schema. It's also portable (the same server works in Claude Desktop, Cursor,
etc.).

**Transport:** local single-user DB → **stdio**. Hermes supports local stdio
servers and remote HTTP/SSE servers in the same config; for a local file, stdio
is right — Hermes launches the server (`command` + `args`) and the client
manages its lifecycle. (If the DB ever goes remote, switch that entry to a
`url` + `headers` HTTP/SSE server — still better than raw REST.)

**Registration:** add a named entry under `mcp_servers:` in Hermes's YAML
config (`~/.hermes/config.yaml`), or run `hermes mcp add`. MCP support installs
via the `.[mcp]` extra (already included in the standard install). Illustrative
entry — see `hermes-agent.nousresearch.com/docs` for the full reference:

```yaml
mcp_servers:
  quantified-self:
    command: "python"
    args: ["-m", "qs_mcp"]
    env:
      QS_DB_PATH: "/home/user/health/app.db"
    timeout: 30
    # Per-server tool filtering — expose only what this profile should see:
    tools:
      include: [query, daily_summary, add_metric, add_note, log_food, log_workout]
    resources: true    # serve the schema resource (section 5)
    prompts: false
```

**Use the filtering as a second safety layer.** Hermes's per-server
`tools.include`/`exclude` lets you control which of your server's tools are even
registered, independent of the server itself. Combined with Hermes profiles +
per-server `env`, you can run a read-only profile that exposes only `query` and
the convenience reads, and reserve the write tools for a trusted profile. This
complements — does not replace — the connection-level read-only enforcement in
section 5.

---

## 4. Data access layer: no ORM

The query tool runs SQL the **LLM** wrote at runtime, so an ORM buys nothing on
the read path — you'd bypass it and run raw SQL anyway. Use the raw driver:

- **Python:** stdlib `sqlite3` with `row_factory = sqlite3.Row` (rows → JSON).
- **Node/TS:** `better-sqlite3` (synchronous, fast, ideal for a local file).

A full ORM (SQLAlchemy ORM, Prisma, Peewee) is also a poor fit for this schema
specifically — views, generated columns, `json_extract`, and `CHECK`
constraints are exactly what ORMs model awkwardly. At most, use a light query
builder for the fixed writes. No full ORM.

---

## 5. MCP tool surface

The split follows the read/write asymmetry. The privilege boundary is the
**database connection**, not the tool name or the model's discretion — open
**two connections**: read-only for queries, read-write for the typed writers.

### Read path — one generic tool, free rein

`query(sql) -> rows`

- Free-form `SELECT`. You can't enumerate the questions in advance (mood vs
  training volume lagged two days; LDL across diet changes), and going
  one-tool-per-read-op would re-commit the per-day-files mistake of
  pre-deciding access patterns.
- **Read-only enforced at the connection**, not by inspecting the SQL string
  (CTEs, pragmas, comments, multi-statement all defeat string checks):
  - Python: `sqlite3.connect("file:app.db?mode=ro", uri=True)`
  - TS: `new Database("app.db", { readonly: true })`
- Guards: single statement only; a `LIMIT` / row cap on returned rows (don't
  dump the DB into context); a statement timeout (so a bad query can't hang).
- **Expose the schema** so the model writes good SQL — the DDL + view
  definitions as an MCP **resource**, or baked into the companion SKILL.md.

### Write path — one typed tool per op, no raw SQL

These are the **validation layer**, not pass-throughs. Each runs a fixed
parameterized statement on the read-write connection:

- `add_metric(observed_at, name, value, unit, source)` — check `name` against
  `metric_def`, verify the unit (kg!), enforce FKs before inserting.
- `add_note(noted_at, kind, body)`
- `log_food(consumed_at, food, servings, meal)` — resolve/insert the `food`
  row, then insert `food_log`.
- `log_workout(started_at, sets[])` — insert the `workout` + its
  `exercise_set` children in one transaction.

Never give the LLM arbitrary `INSERT`/`UPDATE`/`DELETE` — that hands it the
mutations the schema exists to prevent (wrong metric names, mixed units, broken
FKs, mass updates).

### Convenience reads (optional, layered on top)

A couple of hot-path read tools over the generic one, so the model doesn't
re-derive gnarly joins every time:

- `daily_summary(start, end)` — wraps `v_daily_summary`.
- (add others only as real patterns emerge.)

These are optimizations over `query`, not a replacement for it.

### Companion skill / instructions

Hermes grows through skill acquisition, so pair the server with a short skill
(or system instructions) that supplies judgment the tools can't:
- All weights are kg.
- Canonical `metric` names and what they mean.
- Prefer the views (`v_daily_summary`, `v_body_comp_daily`,
  `v_blood_results`) over raw tables.

Check the Hermes skill docs for the exact skill format; the content above is
what matters regardless of packaging.

---

## 6. Daily flow & coach

Push-based loop driven by Hermes (scheduled prompts / cron over your chat
platform — Telegram, etc.). Two light daily touchpoints + one weekly review.
Daily cadence keeps friction low; the weekly review surfaces the cross-domain
picture the daily logs can't show on their own.

**Morning — intention (~30s).** Hermes pings: today's alcohol intention (dry,
or a unit limit) + a health intention or two (train? eating/sleep target?).
Written as a `note` (`kind = 'intention'`) to check against in the evening.

**Evening — review.** Asks: drinks (units, or 0), mood, whether you hit the
day's intentions, one line of reflection. Writes `alcohol_units`, `mood`, any
other metrics, and a `note` (`kind = 'review'`). Reflects back the current
dry-day streak + a goal-anchored nudge.

**Weekly — holistic review.** Driven by `query` / `v_daily_summary`: dry days
this week vs last, and the correlations you can't see day to day — alcohol vs
mood, sleep, training volume, scale weight. This is the coaching signal.

**Data:** no schema change. Alcohol = `metric` rows named `alcohol_units` (log
0 on dry days so streaks compute via a query). Intentions and reflections =
`note` rows distinguished by `kind`. Streaks/trends are queries, not stored
state.

### Coaching tone (lives in the companion skill)

Tone is what makes or breaks it. Bake into the instructions:
- Anchor to the user's stated goals; a slip is data, not a verdict.
- Reward consistency over perfection; surface streaks and trends, not failures.
- No shame, no harsh self-talk — a tool that becomes a guilt engine gets
  abandoned.
- Reinforce real-world support: nudge toward people (a friend, a counselor if
  cutting back gets hard); never position the bot as the sole accountability
  partner.

### Companion skill — draft

Standing brief for the coach:

```
You are a daily accountability coach for <user>. Domains: alcohol and general
health (training, sleep, food, body weight, mood).

- All weights/masses are kg. Canonical metric names: alcohol_units, mood,
  sleep_hours, body_weight_kg; training lives in workout / exercise_set.
- Prefer the views (v_daily_summary, v_body_comp_daily) over raw tables.
- Tone: warm, concrete, non-judgmental. A slip is information, not a moral
  failure. Reward consistency over perfection. Never use shame or harsh
  self-talk. If the user is struggling to cut back, gently point them toward
  people and professional support — do not act as their only accountability.
- Always log what the user reports via the write tools (add_metric, add_note,
  log_food, log_workout). Log alcohol as 0 on dry days.
- Keep daily messages short; save depth for the weekly review.
```

Morning prompt:

```
Good morning. Two quick intentions for today:
1. Alcohol — dry day, or a limit?
2. Health — anything you're aiming for (training, food, sleep)?
Reply in a line or two; I'll check in tonight.
```

Evening prompt:

```
Evening check-in:
- Any drinks today? (units, or "none")
- Mood, 1–10?
- Did the day match this morning's intention?
- One line on how it went.
I'll log it and tell you where your streak's at.
```

Weekly prompt:

```
Weekly review. Pulling dry days, mood, sleep, and training for the last 7 days
vs the prior 7, plus any correlations worth noting. Here's what stands out: ...
```

---

## 7. Build order

1. Create the DB from `schema.sql`; seed `exercise` and `metric_def`
   (names, units, reference ranges).
2. Migrate existing data (sets/reps, scale weight) — reconcile units to kg.
3. MCP server skeleton: two connections (ro + rw), `query` tool, schema
   resource.
4. Write tools (`add_metric`, `add_note`, `log_food`, `log_workout`) with
   validation.
5. Convenience read tool(s) + companion skill.
6. Register under `mcp_servers:` in Hermes `config.yaml` (or `hermes mcp add`);
   confirm tool discovery at startup; test text-to-SQL against the views.
7. Import pipeline for DEXA/blood docs: store raw in `document`, promote
   scalars into `metric` via `json_extract`.
8. Wire the coach: load the companion skill, schedule the morning/evening/weekly
   prompts (Hermes cron/triggers), and run a few days to tune tone and friction.
