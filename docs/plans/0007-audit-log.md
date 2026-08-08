# Plan 0007: Append-only audit log

**Status:** Proposed
**Prerequisites:** Plan 0002 (Alembic)
**Recommended before:** Plan 0006 enabling agent write tools

> **Provenance note.** Unlike the other plans, this one has no basis in
> `design/quantified-self-plan.md` — that document contains no audit log. It was
> reconstructed from Pryce's recollection of having designed one. Treat the
> design below as a **proposal to review**, not a record of a prior decision. If
> the original design surfaces (it may be in the unrecovered `schema.sql`), it
> supersedes this.

---

## 1. Why this matters more once the agent can write

Today every mutation comes from one place: Pryce, through the PWA. Provenance is
implicit and reliable.

Plan 0006 changes that. Once `add_metric`, `log_food`, and `log_workout` are
exposed, an LLM writes to the same tables. Three questions become unanswerable
without a record:

- **"Did I log that, or did the agent?"** A weigh-in of 187.4 lb is plausible
  whether typed, MQTT-published, or inferred from a chat message.
- **"What did this look like before?"** `PUT /api/food/{id}` retroactively
  rewrites every past log entry that references that food (Plan 0005 §1). There
  is currently no way to see what the macros used to be.
- **"What did the agent change while I wasn't watching?"** The coaching loop
  (design doc §6) runs on a schedule and writes unattended.

The design doc's own framing supports this. §2 says the tall `metric` table
means *"new measurement = new rows, never a migration"*, and `document` keeps
raw imports whole with a `document_id` back-reference *"for provenance"*. The
instinct is already there; it just isn't generalised to mutations.

**Scope note:** this is a *provenance and recovery* record, not a security
control. It answers "what changed and who changed it" for a single-user personal
database. It is not tamper-proof against someone with write access to the file —
nothing at this layer could be.

**This is not the journal.** Unshaped data awaiting a formal schema goes to
`note` / `document` (`plans/0005-food-and-notes.md` §1a), not here. The two get
conflated because both are append-ish catch-alls, but their guarantees are
opposites: `audit_log` is immutable forever, while journal rows exist precisely
to be restructured and cleaned up once their shape settles. Staging data in an
append-only table can never be corrected — the triggers below would forbid it.

## 2. Design

### Table

```sql
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY,
    changed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    table_name  TEXT NOT NULL,
    row_id      INTEGER NOT NULL,
    op          TEXT NOT NULL CHECK (op IN ('INSERT','UPDATE','DELETE')),
    actor       TEXT NOT NULL DEFAULT 'app',
    old_values  TEXT CHECK (old_values IS NULL OR json_valid(old_values)),
    new_values  TEXT CHECK (new_values IS NULL OR json_valid(new_values))
);
CREATE INDEX ix_audit_log_table_row ON audit_log(table_name, row_id);
CREATE INDEX ix_audit_log_changed_at ON audit_log(changed_at);
```

### Append-only enforcement

The property is enforced in the database, by triggers that abort any attempt to
modify history:

```sql
CREATE TRIGGER audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
```

This is the crux of the design. Enforcing append-only in application code
protects one of the two write paths (ADR-0002) — the agent's connection would be
entirely unguarded. A trigger fires regardless of which process issued the
statement, which is the only place the guarantee can actually live.

### Population

Also by trigger, per audited table, so both writers are covered:

```sql
CREATE TRIGGER audit_metric_update
AFTER UPDATE ON metric
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, old_values, new_values)
    VALUES ('metric', old.id, 'UPDATE',
        json_object('value', old.value, 'unit', old.unit, 'source', old.source),
        json_object('value', new.value, 'unit', new.unit, 'source', new.source));
END;
```

### What to audit

Not everything. Auditing high-volume inserts doubles write cost for little value.

| Table | INSERT | UPDATE | DELETE | Rationale |
|-------|--------|--------|--------|-----------|
| `metric` | ✓ | ✓ | ✓ | Agent-writable; upserts silently overwrite (`qs_mcp.py:170`) |
| `food` | — | ✓ | ✓ | Edits retroactively rewrite history (Plan 0005 §1) |
| `food_log` | — | ✓ | ✓ | Inserts are self-evident; corrections are not |
| `note` | — | ✓ | ✓ | Notes are a record; edits to a record matter |
| `workouts` | — | ✓ | ✓ | Frequent inserts; the interesting event is a change |
| `exercises` | ✓ | ✓ | ✓ | Agent auto-creates these (`qs_mcp.py:271`, gap G6) |

`metric` gets INSERT auditing specifically because `add_metric` upserts on
conflict — an "insert" can silently replace an existing measurement.

## 3. The actor problem

`actor` is the point of the whole exercise, and a SQLite trigger has no idea
which process fired it. Two workable approaches:

**A. Per-connection marker table.** Each writer stamps its identity on connect;
the trigger reads it.

```sql
CREATE TEMP TABLE IF NOT EXISTS session_actor (actor TEXT);
INSERT INTO session_actor VALUES ('agent');
```
The trigger uses
`COALESCE((SELECT actor FROM temp.session_actor LIMIT 1), 'app')`.
`TEMP` tables are per-connection, so this is naturally isolated. Requires the
trigger to tolerate the table not existing — which `COALESCE` over a subquery on
a missing temp table does *not* do gracefully in SQLite. Needs care.

**B. Distinct `source` values, already in the schema.** `metric.source` exists
(`qs_mcp.py:146` defaults to `'manual'`). Have the MCP server pass
`source='agent'` and the audit trigger copy it.

**Recommend B where a `source` column exists, A only if it proves necessary
elsewhere.** B needs no new mechanism and no fragile temp-table handling. Its
limit is that tables without a `source` column can't distinguish actors — which
is an argument for adding `source` to `food_log` and `note` in Plan 0005 rather
than building actor plumbing here.

## 4. Growth and retention

An append-only table only grows. Rough sizing: a few hundred audited mutations a
month at ~200 bytes of JSON each is well under a megabyte a year — negligible
next to the workout data.

But `metric` INSERT auditing plus MQTT scale writes could change that: if the
scale publishes several readings per weigh-in and each becomes an audited row,
volume rises with device chatter rather than with user activity. Check the real
rate after a month:

```sql
SELECT table_name, op, COUNT(*) FROM audit_log
WHERE changed_at > datetime('now','-30 days')
GROUP BY table_name, op ORDER BY 3 DESC;
```

If retention is ever needed, deleting old rows requires dropping the
`audit_log_no_delete` trigger, pruning, and recreating it — deliberately
awkward, and correctly so. Do it in an Alembic revision so it's recorded.

## 5. Surfacing it

Not a UI feature initially. The value is diagnostic, and the natural consumer is
the agent — `query()` reaches `audit_log` through the read-only connection with
no extra work, so "what changed in the last week?" is answerable on day one.

If it later deserves a UI, a per-row history on the food edit screen is the
strongest candidate, since that's where invisible retroactive rewrites happen.

## 6. Verification

```sql
-- append-only actually holds
INSERT INTO audit_log (table_name, row_id, op) VALUES ('test', 1, 'INSERT');
UPDATE audit_log SET op = 'DELETE' WHERE table_name = 'test';
-- -> Error: audit_log is append-only
DELETE FROM audit_log WHERE table_name = 'test';
-- -> Error: audit_log is append-only

-- capture works and records both sides
UPDATE food SET kcal_per_serving = 80 WHERE name = 'Egg';
SELECT table_name, op, old_values, new_values FROM audit_log ORDER BY id DESC LIMIT 1;
```

Test that the triggers fire for writes made **outside** SQLAlchemy — connect
with raw `sqlite3` as the MCP server does and confirm the row still appears.
That is the case application-level auditing would miss, and the reason this is
built with triggers.

## 7. Rollback

Drop the triggers, then the table. The `no_delete` trigger must be dropped
before the table can be, which is itself a small demonstration that the
enforcement works.

## 8. Open questions

1. Does this match the original design, or was that something else — an
   event-sourced log as the *primary* store rather than a side record?
2. Should `document` inserts be audited, or is that table already append-only by
   convention?
3. Is per-row UI history wanted, or is agent-queryable enough?
