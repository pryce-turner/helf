# Plan 0011: Supplement stacks

**Status:** Implemented (2026-08-09) — revision `9ffbe9c21a0f`
**Prerequisites:** Plan 0005 ✓ (`food`, `food_log`), Plan 0007 ✓ (audit log)
**Related:** ADR-0003, ADR-0006

A named group of consumables that can be logged in one action. Morning is
omega, vitamin D and CholestOff; evening is magnesium and omega; creatine and
whey are whenever.

---

## 1. Supplements are `food` rows

The obvious design is a `supplement` table and a `supplement_log`. It is the
wrong one, and the reason is whey protein.

A supplement is a thing with a serving size that you swallow at a time,
recorded with a timestamp and an amount. That is exactly what `food` and
`food_log` already model. And the boundary between the two categories is not
where a schema can put it: **whey is food by any definition**, at 120 kcal a
scoop, and a mass gainer is 1,200. Filing those anywhere but `food_log` either
duplicates them or hides them from `v_daily_summary.kcal`, which is the number
the whole calorie loop exists to compute.

A parallel table would also have meant: a second logging path for the agent to
learn, its own audit triggers, its own subqueries in the daily view, and a
`unit` column — the thing ADR-0003 removed from this schema.

So supplements go in `food`, and the only genuinely new thing here is the
**grouping**. That is all this plan adds: `stack` and `stack_item`.

### `food.kind`

```sql
ALTER TABLE food ADD COLUMN kind TEXT NOT NULL DEFAULT 'food'
  CHECK (kind IN ('food','supplement'));
```

Two jobs. It keeps each page's typeahead to its own vocabulary — a search for
"ma" reaches both Mango and Magnesium — and it fixes a false alarm this feature
would otherwise create in `v_daily_summary`:

> `foods_missing_macros` counts logged foods with any unknown macro, so that a
> partially catalogued day reports a confident low protein total *and says so*.
> A vitamin has no macros to be missing. Without the filter, every dose of
> creatine would report the day as understated, permanently, on a page whose
> whole job is to be trusted about calories.

`ADD COLUMN` with a `CHECK` is legal in SQLite and is enforced — verified
against a scratch database rather than assumed, because a silently unenforced
constraint here would let the agent invent a third kind.

## 2. `food_log` gains no `stack_id`

This is the load-bearing decision.

A logged row records **what was consumed**. The stack is the *input method*.
Pointing history at a preset that can be edited later is the same retroactive
rewrite as editing a food's macros (Plan 0005 §1), except about what happened
rather than what it contained — and unlike macros, there is no version of that
which is desirable.

The cost looks like losing "did I take my morning stack today?". It isn't:

```sql
-- taken == every one of the stack's foods appears in that day's log
SELECT COALESCE(MIN(EXISTS (
    SELECT 1 FROM food_log fl WHERE fl.food_id = si.food_id AND fl.date = ?
)), 0)
FROM stack_item si WHERE si.stack_id = ?
```

That phrasing is *truer* than a marker would be, because it holds whether the
button was tapped or the three items were entered by hand. `COALESCE` matters:
`MIN()` over no rows is NULL, and without it an empty stack would report itself
as taken every day.

## 3. Shape

```sql
CREATE TABLE stack (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    note TEXT,
    "order" INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE stack_item (
    id INTEGER PRIMARY KEY,
    stack_id INTEGER NOT NULL REFERENCES stack(id) ON DELETE CASCADE,
    food_id  INTEGER NOT NULL REFERENCES food(id),
    servings REAL NOT NULL DEFAULT 1.0,
    "order"  INTEGER NOT NULL DEFAULT 1,
    UNIQUE (stack_id, food_id)
);
```

- **`servings` is on the membership, not the food.** Two omega capsules in the
  morning and one in the evening is one product taken two ways.
- **`UNIQUE (stack_id, food_id)`** — the same vitamin twice in one group is
  always a mistake, and it would silently double the dose on every log. The
  repository catches it first so the caller gets a sentence instead of an
  `IntegrityError` naming a constraint they cannot see.
- **`ON DELETE CASCADE` on `stack_id`, and deliberately *not* on `food_id`.**
  Deleting a stack drops its membership and nothing else — the foods and every
  past `food_log` row survive, because they are history and the stack never
  owned them. Deleting a food that a stack still uses is refused by the FK,
  which is the honest outcome for something in use.

### Dose is prose

`food.serving_desc` holds "1 softgel, 1000mg EPA"; the page renders it beside
`servings` as "2 × 1000mg EPA". That is enough to answer *what am I taking and
how much*, and it is not enough to do arithmetic on.

Structured dose needs an amount and a unit per substance, and the place for
that already exists: a `metric_def` entry plus `metric` rows, where the unit is
fixed by the name so `vitamin_d_iu` cannot become mcg on a later Thursday. The
promotion pathway is Plan 0005 §1a — do it when a supplement earns the
migration, not for the whole shelf up front.

## 4. `v_daily_summary` gains one column, not one per supplement

```sql
(SELECT COUNT(*) FROM food_log fl JOIN food f ON f.id = fl.food_id
  WHERE fl.date = d.date AND f.kind = 'supplement') AS supplements_taken
```

*Which* supplements were taken is a `food_log` question. The daily row only has
to say whether the day had any, so the column list cannot grow with the shelf —
which is what a column per supplement would be, and what retiring
`body_composition` in Plan 0010 was about.

## 5. Surface

`POST /api/stacks/{id}/log` writes one `food_log` row per item at one instant,
in one transaction — a stack half-logged is worse than not logged, because the
missing half is invisible. Rows carry **no meal**: swallowing omega at 7am is
not breakfast, and filing it as one would inflate a meal with things nobody
ate. The Food tab groups supplements separately for the same reason.

`PUT /api/stacks/{id}` with `items` **replaces** the membership rather than
merging. A group is edited as a list — "these are the three things I take in
the morning" — and a merge makes removing one require a call the UI has no
natural place for.

Front end: a third tab in the Body section, which is what ADR-0006 said
`SectionTabs` was a list for.

## 6. Verification

Against a `.backup` copy of production, with the real stacks:

| | |
|---|---|
| Morning / Evening / Anytime created, omega shared | 2 servings in Morning, 1 in Evening, one catalog row |
| Logged Morning + Anytime | `taken_today` true for both, false for Evening |
| Day totals | kcal 120, protein 25 — **whey only**; the other four contributed nothing |
| `foods_missing_macros` | **0**, with four macro-less supplements logged |
| `supplements_taken` | 5 |
| `kcal_target` | 2730, unchanged |
| Edited Morning to drop CholestOff | today's five logged entries unchanged |
| Audit log | three `stack_item` DELETEs with old values, actor `app` |
| `DELETE FROM food` for a food in a stack | `FOREIGN KEY constraint failed` |

`pytest` 302 passed (17 new), `alembic check` clean, ruff and eslint clean.

## 7. Rollback

`downgrade()` drops `stack_item`, `stack` and the audit triggers, rebuilds
`v_daily_summary` without `supplements_taken` and without the `kind` filter,
and drops `food.kind` — which turns supplements back into ordinary foods rather
than deleting them, since the log rows referencing them are real consumption
events either way.
