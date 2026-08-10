# Plan 0007: Append-only audit log

**Status:** Implemented (2026-08-09) — revision `7e8f2b1ca79b`; **§3's actor
design is impossible in SQLite and was replaced**, see §9
**Prerequisites:** Plan 0002 (Alembic) ✓
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

## 9. What actually landed (2026-08-09, revision `7e8f2b1ca79b`)

### §3's option A is not implementable. Neither is option B.

**Option A — a per-connection `TEMP` marker table — cannot be built in SQLite.**
Two independent failures, both confirmed against a scratch database rather than
argued from the documentation:

```
CREATE TRIGGER t AFTER INSERT ON thing BEGIN
  INSERT INTO log ... (SELECT actor FROM temp.session_actor LIMIT 1) ...
END;
-- Error: in prepare, trigger t cannot reference objects in database temp
```

Dropping the `temp.` qualifier in the hope that a connection's temp table
shadows the main one does not work either: name resolution binds when the
trigger is compiled, so a connection that creates `TEMP session_actor` and
writes still gets the value from `main`. The scratch test wrote `'app'` for a
connection that had explicitly declared itself `'agent'` — a silent wrong
answer, which is the worst possible failure for a provenance record.

**Option B — reuse `metric.source` — describes a column that no longer
exists.** Plan 0003 moved `source` onto `observation`, and it is an
*instrument* ('openscale', 'bodyspec'), not an actor. Conflating the two would
make "which of these did the agent write?" unanswerable for exactly the rows
where it matters.

### What replaced them: a permanent marker plus SQLite's write lock

```sql
CREATE TABLE audit_actor (
    id    INTEGER PRIMARY KEY CHECK (id = 1),
    actor TEXT NOT NULL DEFAULT 'app'
);
```

One row, enforced by the CHECK. The isolation that `TEMP` was supposed to
provide comes from SQLite's **single-writer** rule instead: a writer that takes
the write lock *before* claiming the actor cannot have another writer's rows
attributed to it. `docs/reference/qs_mcp.py`'s `_rw()` is now a context manager
that does exactly this, in this order:

1. `BEGIN IMMEDIATE` — take the write lock first.
2. `UPDATE audit_actor SET actor = 'agent'`.
3. the writes.
4. `UPDATE audit_actor SET actor = 'app'` **inside the same transaction**, so a
   crash rolls the claim back with everything else. Without step 4 an aborted
   agent write would silently misattribute every subsequent write the PWA made.

The default is `'app'` and is never wrong by accident: a writer that says
nothing is the PWA, and the only other writer has to opt in explicitly.

### The migration tests its own guarantee

`CREATE TRIGGER` being accepted is not evidence that a trigger fires, so the
migration inserts a probe row, attempts an `UPDATE` and a `DELETE`, and fails
loudly if either is permitted. The whole probe runs in a savepoint that is
rolled back — the row could not be cleaned up otherwise, which is precisely
what is being verified.

### Audited tables

As §2's matrix, unchanged. Column capture is per table, and `workouts`'
`order` column is quoted in the generated `json_object(...)` — it is a reserved
word and produces a syntax error otherwise. There is a test for that
specifically.

Cascaded deletes were the one uncertainty: deleting an `observation` removes
its metrics by `ON DELETE CASCADE`, and it was not obvious the `AFTER DELETE`
trigger would fire without `PRAGMA recursive_triggers`. It does, verified both
in a scratch database and in the suite.

### Verification

`backend/tests/test_db_audit_log.py`, 13 tests. Every case where coverage is
the point writes through a **raw `sqlite3` connection**, not the ORM — that is
the path application-level auditing would miss and the reason this is built out
of triggers at all.

Against `data/helf.db` (backed up to `helf.db.pre-0007.bak` first): 16 triggers
created, `audit_log` empty, `audit_actor` = 'app'. A probe that claimed the
agent actor, touched a real workout row, and rolled back produced an audit row
reading `workouts | UPDATE | agent | 110.0` inside the transaction and left
zero rows and `actor = 'app'` after the rollback.
