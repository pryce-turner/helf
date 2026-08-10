# Plan 0004: Workout session regrain

**Status:** Deferred — designed, and recommended to stay deferred; see §1
**Prerequisites:** Plans 0002, 0003
**Related:** Plan 0001 §3

Converts the flat `workouts` table into the design doc's
`workout` → `exercise_set` hierarchy. This plan exists so the work is understood
and costed. **The recommendation is not to do it yet.** §5 gives the reasoning.

---

## 1. The grain mismatch

Today (`backend/app/db/models.py:48-76`), a `workouts` row is **one logged
entry** — a single exercise with a single weight/reps pair, positioned by
`order` within a `date`:

```
workouts: (id, date, exercise_id, category_id, weight, reps, distance,
           time, comment, order, completed_at, ...)
```

There is no session entity. "A workout" is an emergent grouping — every row
sharing a `date`. Multiple sets of the same lift are multiple rows sharing
`(date, exercise_id)`, distinguished by `order`.

The design doc wants three levels:

```
workout (session):  id, started_at, notes
exercise_set:       id, workout_id, exercise_id, set_number, reps, weight_kg, rpe
```

So the change is: **synthesise a session parent from date groupings, and demote
existing rows to children.**

## 2. Migration shape

```sql
-- one session per distinct date
INSERT INTO workout (started_at, notes)
SELECT DISTINCT date || 'T00:00:00', NULL FROM workouts;

-- each existing row becomes a set, order -> set_number
INSERT INTO exercise_set (workout_id, exercise_id, set_number, reps, weight_kg)
SELECT w.id, old.exercise_id, old."order", old.reps, old.weight
FROM workouts old
JOIN workout w ON w.started_at = old.date || 'T00:00:00';
```

Mechanically straightforward. The problems are in what doesn't map.

### What doesn't map cleanly

Measured against the production copy (`data/helf.db`, 9,292 rows):

| Current column | Non-null | Fate |
|----------------|----------|------|
| `distance`, `distance_unit` | **0** | Never used. Drop rather than migrate — this concern was overstated in an earlier draft |
| `time` | 35 | No home in `exercise_set`; 35 rows is small enough to migrate to `note` or accept losing |
| `comment` | 462 | Per-entry today; the design doc has per-session `workout.notes` plus a `note` table. Needs a real decision, not a default |
| `completed_at` | 9,274 | **Almost universal.** Set-completion state is load-bearing UI, and the target schema has no equivalent |
| `category_id` | — | Denormalised onto each row today; reachable via `exercise` in the target. Dropping it changes query shape in `workout_repo.py` |
| `order` | — | Becomes `set_number`, but the semantics differ — `order` sequences *entries within a day* across different exercises; `set_number` sequences *sets within an exercise* |

Scale of the migration: **9,292 rows across 639 distinct training days and 170
exercises**, spanning 2018-04-02 → 2026-07-08. Eight years of history, which
raises the cost of getting the regrain wrong considerably.

That last row is the subtle one. `order` is a display ordering across the whole
session; `set_number` is per-exercise. They are not the same field, and a
straight copy produces sets numbered 7, 8, 9 for the third exercise of the day.
Correct migration requires renumbering per `(date, exercise_id)` with a window
function, and separately preserving display order on the session.

**`started_at` loses information in the other direction too**: the current schema
stores only a `date`, so every migrated session gets a synthetic midnight
timestamp. Real session start times cannot be recovered.

## 3. Blast radius

### Backend

- `backend/app/repositories/workout_repo.py` (348 lines) — near-total rewrite
- `backend/app/services/progression_service.py:55,130` — reads flat rows
- `backend/app/services/wendler_service.py` — `get_latest_estimated_1rm` queries by exercise
- `backend/app/api/workouts.py` — every endpoint, especially `PATCH /{id}/reorder`
- `backend/app/models/workout.py` — response shape changes

### Frontend

- `frontend/src/pages/WorkoutSession.tsx` — **1,626 lines**, the largest file in
  the frontend. Carries drag-to-reorder, inline expansion editing, set
  completion, duplicate, and move-to-date
- `frontend/src/pages/Calendar.tsx` — counts per date
- `frontend/src/pages/Progression.tsx`, `Upcoming.tsx`
- `frontend/src/hooks/useWorkouts.ts`, `frontend/src/types/workout.ts`

### The reorder contract

`PATCH /api/workouts/{id}/reorder` and the `ix_workouts_date_order` index
(`db/models.py:53`) are built directly on flat `(date, order)`. Reordering
across a hierarchy means either reordering sets within an exercise or exercises
within a session — two different operations where there is currently one. The
drag-and-drop UI (commit `2ee4223`) has to be reworked to express which.

## 4. Why the MCP server doesn't need this

`reference/qs_mcp.py:250` implements `log_workout(sets[], started_at, notes)`,
which assumes the hierarchy. That is the only real pull toward doing the regrain.

It's satisfiable with an adapter instead. `log_workout` writes N flat `workouts`
rows sharing a date, assigning `order` sequentially:

```python
# adapter: hierarchical tool signature, flat storage
for i, s in enumerate(sets, start=1):
    conn.execute(
        """INSERT INTO workouts (date, exercise_id, category_id, weight, reps, "order",
                                 created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (started_at[:10], eid, cid, s.weight_kg, s.reps, i, now, now),
    )
```

The tool's *interface* stays as designed — the agent still speaks sessions and
sets. Only storage differs. Since the agent never sees the schema except through
`get_schema` and the views, and the views can present either shape, the
hierarchy is not observable from where it would matter.

## 5. Recommendation

**Defer indefinitely; revisit when a feature actually requires it.**

The cost is a rewrite of the largest frontend file, the largest repository, and
the reorder contract — plus lossy handling of `distance`, `time`, `comment`, and
`completed_at`, and unrecoverable session start times.

The benefit is modelling purity. Nothing the design doc actually asks for
requires it:

- `v_daily_summary` groups by `date`, which the flat table already has
- Cross-domain queries join on `date`, not on session identity
- `log_workout` works via the adapter above
- Progression already works on flat rows

The honest trigger for doing this work is a **feature that needs session
identity** — session duration, rest timing, per-session RPE, "same workout as
last Tuesday". None of those are on the roadmap. Until one is, this is churn
with a real chance of data loss and no user-visible gain.

If it does happen: do it as its own release with the DB copy from Plan 0003 §1,
migrate to the new tables while keeping `workouts` intact and dual-read for at
least one full training cycle, and only then drop the old table.
