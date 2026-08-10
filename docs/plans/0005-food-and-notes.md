# Plan 0005: Food and notes

**Status:** Proposed — **partially landed**: `document` was created by Plan 0008, see below
**Prerequisites:** Plan 0002 (Alembic)
**Related:** Plan 0001 §3

Adds calorie/macro tracking, first-class notes, and the `document` table. All
three are **purely additive** — new tables, no migration of existing data, no
change to any existing endpoint.

This is the lowest-risk phase and the one carrying the feature that motivated
the design doc. It can ship independently of Plan 0003.

---

## 1. Schema

Constrained by `reference/qs_mcp.py` — `log_food` (line 200) resolves a `food`
row by `(name, brand)` then inserts into `food_log`, so those columns must exist
with those names.

```sql
CREATE TABLE food (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    brand             TEXT,
    serving_desc      TEXT,
    kcal_per_serving  REAL,
    protein_g         REAL,
    carb_g            REAL,
    fat_g             REAL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, brand)
);

CREATE TABLE food_log (
    id           INTEGER PRIMARY KEY,
    consumed_at  TEXT NOT NULL,
    date         TEXT GENERATED ALWAYS AS (substr(consumed_at, 1, 10)) STORED,
    food_id      INTEGER NOT NULL REFERENCES food(id),
    servings     REAL NOT NULL DEFAULT 1.0,
    meal         TEXT CHECK (meal IN ('breakfast','lunch','dinner','snack') OR meal IS NULL),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_food_log_date ON food_log(date);

CREATE TABLE note (
    id        INTEGER PRIMARY KEY,
    noted_at  TEXT NOT NULL,
    date      TEXT GENERATED ALWAYS AS (substr(noted_at, 1, 10)) STORED,
    kind      TEXT,
    body      TEXT NOT NULL
);
CREATE INDEX ix_note_date_kind ON note(date, kind);

-- ALREADY EXISTS. Created by Plan 0008 (revision 61ccf127e583) with one extra
-- column; do NOT create it again. See the note below.
CREATE TABLE document (
    id           INTEGER PRIMARY KEY,
    imported_at  TEXT NOT NULL DEFAULT (datetime('now')),
    kind         TEXT NOT NULL,
    source       TEXT,
    external_id  TEXT,                 -- added by 0008: upstream identity
    raw          TEXT NOT NULL CHECK (json_valid(raw))
);
CREATE UNIQUE INDEX ux_document_kind_external ON document(kind, external_id);
```

> **`document` has already landed.** Plan 0008 needed it before this plan was
> scheduled — for DEXA payload retention and for `result_id` idempotency — so it
> created the table to this spec, plus `external_id` and the unique index over
> `(kind, external_id)`, and added `metric.document_id`. Revision
> `61ccf127e583`.
>
> This plan must therefore **not** create `document`, and its migration should
> guard on the table already existing rather than assume a clean slate. There
> are live rows in it: four DEXA documents as of 2026-08-09.
>
> `external_id` is nullable and SQLite treats NULLs as distinct in a unique
> index, so the notes and food imports this plan describes — which have no
> upstream identity — coexist freely under the constraint.

### Notes on the shape

- **`UNIQUE (name, brand)` and NULL brands.** `log_food` looks up with
  `WHERE name = ? AND brand IS ?` (`qs_mcp.py:219`) — note `IS`, not `=`, which
  is correct for NULL matching in SQLite. But SQLite's `UNIQUE` treats NULLs as
  distinct, so the constraint will *not* prevent duplicate `('Chicken', NULL)`
  rows. Either store `''` instead of NULL for brandless foods, or accept that
  the constraint is advisory here. **Recommend `''`** — it makes the constraint
  real and the lookup a plain `=`. This requires a one-line change to
  `qs_mcp.py`.

- **Macros live on `food`, not `food_log`.** A serving's macros are derived
  (`servings × kcal_per_serving`), not stored. This is right — it means fixing a
  food's macros retroactively corrects every past log entry. It also means
  editing a shared food rewrites history, which is exactly the kind of silent
  mutation Plan 0007's audit log is for.

- **`kind` on `note` is intentionally unconstrained.** The design doc §6 uses
  `'intention'` and `'review'`; workouts would use `'workout'`, injuries
  `'injury'`. Adding a `CHECK` here would need a migration every time the
  coaching loop grows a new note type.

- **`document.raw` uses `json_valid`**, per the design doc §2, so malformed
  imports fail at insert rather than at read.

## 1a. The journal: where unshaped data lands

**Requirement:** anything without a settled shape goes somewhere durable now and
gets migrated into a formal schema later.

`note` and `document` *are* that landing zone. They need no new table — but they
do need an explicit promotion pathway, or the journal becomes a write-only pile.

### Not the audit log

These are frequently conflated and must not share a table:

| | `audit_log` (Plan 0007) | `note` / `document` (the journal) |
|---|---|---|
| Records | Mutations to other tables | Observations about the world |
| Written by | Database triggers | You and the agent |
| Lifecycle | **Immutable forever** | Staging — expected to be superseded |
| Grows | With every edit | With every observation |

The audit log's whole value is that nothing can rewrite it. The journal's whole
value is that its contents *will* be restructured. Putting staging data in an
append-only table means the day you formalise a shape, the raw rows can never be
cleaned up or corrected. Keep them separate.

### Which table

| Data | Table | Example |
|------|-------|---------|
| Prose, no fixed fields | `note` | "left knee tweaked on set 3", a training reflection |
| Structured, shape not yet modelled | `document` | An API payload, a CSV import, a device export |
| A named scalar over time | **`metric`** — not the journal | Sleep hours, mood, alcohol units |

That third row matters. A number with a name and a unit already has a shape;
`metric` plus a `metric_def` entry is the formal schema, and routing scalars
through the journal instead just defers work with no benefit.

### Give `note` a `source`

```sql
ALTER TABLE note ADD COLUMN source TEXT NOT NULL DEFAULT 'manual';
```

Once the agent can write notes (Plan 0006), "did I observe this or did the model
infer it?" is unanswerable without it. Same argument as `metric.source`, and
cheaper to add now than to backfill.

### The promotion pathway

Journal → formal schema is the same move Plan 0008 makes for DEXA: keep the raw
row, extract the scalars, link back by `document_id`.

1. A shape recurs often enough to be worth querying.
2. Add a `metric_def` entry (or a table, if genuinely relational).
3. Backfill from the stored rows — `json_extract` for `document`, by hand for
   `note`.
4. **Keep the source rows.** Promotion is additive. The raw record stays as
   provenance, exactly as `document.raw` does for BodySpec, so a mistaken
   extraction can be redone without re-fetching anything.

This is why `document.raw` has a `json_valid` CHECK: a landing zone that accepts
malformed payloads cannot be promoted from later.

### Review it periodically

The failure mode is silt — a journal accumulating rows nobody revisits. One
query, worth running occasionally:

```sql
SELECT kind, count(*) AS n, min(date) AS first, max(date) AS last
FROM note GROUP BY kind
UNION ALL
SELECT 'doc:'||kind, count(*), min(imported_at), max(imported_at)
FROM document GROUP BY kind;
```

Any `kind` with a steady accumulation and a long history is a shape asking to be
formalised.

## 2. Backend

Follows the existing layering (`CLAUDE.md` — "Add a new API endpoint"):

| Layer | File | Content |
|-------|------|---------|
| ORM | `backend/app/db/models.py` | `Food`, `FoodLog`, `Note`, `Document` |
| Pydantic | `backend/app/models/food.py`, `note.py` | Create/response models |
| Repository | `backend/app/repositories/food_repo.py`, `note_repo.py` | Data access |
| API | `backend/app/api/food.py`, `notes.py` | Route handlers |
| Register | `backend/app/main.py` | `app.include_router(...)` |

### Generated columns and SQLAlchemy

`date` is a SQLite `GENERATED ALWAYS ... STORED` column. SQLAlchemy must be told
not to write to it:

```python
date: Mapped[str] = mapped_column(
    String(10),
    Computed("substr(consumed_at, 1, 10)", persisted=True),
    index=True,
)
```

Without `Computed`, inserts fail with *"cannot INSERT into generated column"*.
This is the most likely thing to go wrong in this plan, and it fails loudly.

### Endpoints

```
GET    /api/food/log?date=YYYY-MM-DD     entries for a day
GET    /api/food/log/summary?start&end   daily kcal + macro totals
POST   /api/food/log                     log a consumption event
DELETE /api/food/log/{id}
GET    /api/food?q=                      search the catalog
POST   /api/food                         create a food
PUT    /api/food/{id}                    edit macros
GET    /api/notes?kind=&start=&end=
POST   /api/notes
```

The summary endpoint carries the only real logic:

```sql
SELECT fl.date,
       SUM(f.kcal_per_serving * fl.servings) AS kcal,
       SUM(f.protein_g        * fl.servings) AS protein_g,
       SUM(f.carb_g           * fl.servings) AS carb_g,
       SUM(f.fat_g            * fl.servings) AS fat_g
FROM food_log fl JOIN food f ON f.id = fl.food_id
WHERE fl.date BETWEEN ? AND ?
GROUP BY fl.date;
```

`SUM` over NULL macros yields NULL, not 0 — a food with unknown protein makes
the whole day's protein NULL. Use `COALESCE(f.protein_g, 0)` if partial totals
are preferable to a null, and surface "N foods missing macros" in the UI so the
gap is visible rather than silently zeroed.

## 3. `v_daily_summary`

The design doc calls this *"the single most useful object to hand the LLM"*. It
can be built once food exists, and is the join point for everything else.

```sql
CREATE VIEW v_daily_summary AS
WITH days AS (
    SELECT date FROM workouts
    UNION SELECT date FROM food_log
    UNION SELECT date FROM metric
    UNION SELECT date FROM note
)
SELECT
    d.date,
    (SELECT COUNT(*) FROM workouts w WHERE w.date = d.date)                       AS sets_logged,
    (SELECT SUM(w.weight * CAST(REPLACE(w.reps,'+','') AS INTEGER))
       FROM workouts w WHERE w.date = d.date AND w.reps IS NOT NULL)              AS training_volume_lb,
    (SELECT SUM(f.kcal_per_serving * fl.servings)
       FROM food_log fl JOIN food f ON f.id = fl.food_id WHERE fl.date = d.date)  AS kcal,
    (SELECT value FROM metric m
       WHERE m.date = d.date AND m.name = 'body_weight_lb' LIMIT 1)               AS body_weight_lb,
    (SELECT value FROM metric m
       WHERE m.date = d.date AND m.name = 'mood' LIMIT 1)                         AS mood
FROM days d;
```

Two dependencies worth stating:

- The `days` spine is a `UNION` of dates, per the design doc §2 — no separate
  day table.
- `metric` only exists after Plan 0003. If food ships first, build this view
  without the `metric` columns and extend it in 0003. **Views are cheap to
  replace** (`DROP VIEW` / `CREATE VIEW`, no data risk), which is exactly why
  they're the right interface to give the agent.
- `training_volume_lb` is safe to ship immediately. `workouts` is already
  uniformly lbs (9,292/9,292), so this column is correct whether or not Plan 0003
  has run — one consequence of ADR-0003 choosing the unit the data was already
  in. Only the `metric`-derived columns wait on Plan 0003.

## 4. Frontend

New page, following `CLAUDE.md`'s "Add a new frontend page":

- `frontend/src/pages/Food.tsx` — daily log, running kcal/macro totals
- `frontend/src/hooks/useFood.ts`, `frontend/src/types/food.ts`
- Route in `frontend/src/App.tsx`, nav entry in `Navigation.tsx`

**Navigation is past capacity.** `Navigation.tsx:14-18` now carries **five**
items — Calendar, Progress, Body, Upcoming, Exercises — after merge `1a27a0b`
added the Exercises page. Three separate commits have been navbar spacing fixes
(`7aa5f44`, `accd72a`, `cd5f32d`), plus one for double-tap (`c64434e`).

A Food page would be the **sixth**. That is a layout decision — overflow menu,
grouping, or a different navigation pattern — not an insertion. Settle it before
building the page, since it may change where food lives (e.g. a tab under Body
rather than a peer of it).

Design-system notes: `.stat-card` for the kcal/macro row, `--chart-1..5` for
macro breakdown, `<Input>` for entry. Numeric inputs need the mobile keyboard
fix from commit `439db1d` — check how `WorkoutSession.tsx` sets `inputMode`.

## 5. Verification

```sql
INSERT INTO food (name, brand, kcal_per_serving, protein_g) VALUES ('Egg', '', 78, 6.3);
INSERT INTO food_log (consumed_at, food_id, servings, meal)
VALUES ('2026-08-07T08:00:00', 1, 2, 'breakfast');
SELECT date, servings FROM food_log;      -- date auto-populates -> 2026-08-07
SELECT * FROM v_daily_summary WHERE date = '2026-08-07';   -- kcal = 156
```

Tests: `backend/tests/test_repositories_food.py`,
`backend/tests/test_api_food.py`, following the existing patterns in
`test_api_workouts.py`. Cover the NULL-macro summation case explicitly — it's
the one piece of real logic here.

## 6. Rollback

`DROP TABLE food_log, food, note, document` and drop the view. No existing data
is touched by this plan, so rollback is complete and safe.
