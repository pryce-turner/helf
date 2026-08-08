# Plan 0009: Drop AMRAP notation — `reps` becomes an integer

**Status:** Proposed
**Prerequisites:** Plan 0002 (Alembic)
**Related:** ADR-0005
**Risk:** Low — verified lossless against production data

Small, self-contained, and worth doing early: it removes a silent-wrong-answer
class from every numeric query on `reps`, including the LLM-authored ones the
MCP server will run.

---

## 1. Verified lossless

Against `data/helf.db`:

```sql
SELECT reps, count(*) FROM workouts
WHERE reps IS NOT NULL AND CAST(reps AS INTEGER)||'' <> reps
GROUP BY 1;
-- returns nothing: all 9,252 non-null values are exact integers

SELECT reps, count(*) FROM upcoming_workouts GROUP BY 1;
-- 5|18  10|8  6|4
```

Zero `+`, zero non-numeric, zero empty strings, 40 NULLs in `workouts`. `CAST`
is exact for every row.

**Re-run both checks immediately before migrating.** They are instant, and the
guarantee only holds for the data as it is now — a single AMRAP row entered
between now and then would be silently truncated by `CAST` (`'5+'` → `5`).

## 2. Migration

SQLite cannot alter a column type in place, so this needs Alembic's batch mode
(`render_as_batch=True`, Plan 0002 §1.4), which rebuilds the table.

```python
def upgrade():
    for table in ("workouts", "upcoming_workouts"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "reps",
                existing_type=sa.String(16),
                type_=sa.Integer(),
                existing_nullable=True,
                postgresql_using=None,   # SQLite: rebuild handles the cast
            )
```

**Guard the migration.** A batch rebuild is a table copy; if a `+` row exists it
casts to a wrong integer with no error. Fail loudly instead:

```python
bad = conn.execute(sa.text(
    "SELECT count(*) FROM workouts "
    "WHERE reps IS NOT NULL AND CAST(reps AS INTEGER)||'' <> reps"
)).scalar()
if bad:
    raise RuntimeError(f"{bad} non-integer reps values — resolve before migrating")
```

`workouts` also carries `ix_workouts_date_order` (`db/models.py:52`); confirm
indexes survive the rebuild, since batch mode recreates them from metadata.

## 3. Code changes

| File | Change |
|------|--------|
| `backend/app/db/models.py:64,93` | `String(16)` → `Integer` on both `reps` columns |
| `backend/app/models/workout.py` | Pydantic `reps: str \| None` → `int \| None` |
| `backend/app/models/upcoming.py` | Same |
| `backend/app/utils/calculations.py:4-28` | Signature `int`; delete the string branch and the `except → 0.0` |
| `backend/app/services/wendler_service.py:44-49` | `'5+'`/`'3+'`/`'1+'` → `5`/`3`/`1` |
| `frontend/src/types/workout.ts`, `upcoming.ts` | `reps: string` → `number` |
| `frontend/src/pages/WorkoutSession.tsx` | Rep input parses to number; keep `inputMode="numeric"` (commit `439db1d`) |

### `calculate_estimated_1rm`

Before — accepts either type, swallows failure:

```python
def calculate_estimated_1rm(weight: float, reps: int | str) -> float:
    try:
        reps_num = int(reps.replace("+", "")) if isinstance(reps, str) else int(reps)
        ...
    except (ValueError, TypeError):
        return 0.0
```

After:

```python
def calculate_estimated_1rm(weight: float, reps: int) -> float:
    """Epley: (0.033 x reps x weight) + weight."""
    return round((0.033 * reps * weight) + weight, 1)
```

**Deleting the `except` is the point, not incidental.** Returning `0.0` for
unparseable input puts a fake data point on a progression chart that looks like
a real measurement of zero. Callers must now handle `None` reps before calling —
`progression_service.py` already filters on `w.get('reps')`.

### Wendler generator

```python
WEEK_PERCENTAGES = {
    1: [(0.65, 5), (0.75, 5), (0.85, 5)],   # was '5+'
    2: [(0.70, 3), (0.80, 3), (0.90, 3)],   # was '3+'
    3: [(0.75, 5), (0.85, 3), (0.95, 1)],   # was '1+'
    4: [(0.40, 5), (0.50, 5), (0.60, 5)],   # deload, unchanged
}
```

The return type annotation `list[tuple[int, int | str]]`
(`wendler_service.py:84`) narrows to `list[tuple[int, int]]`.

This changes what the generator writes but **not the programme** — the top set of
weeks 1–3 is still intended as AMRAP in
`PryceVault/Lifting/1000lb Program.md`. That intent now lives in the programme,
not the row. Worth a line in the generator's docstring so the omission reads as
deliberate.

## 4. Verification

```sql
-- type is integer and comparisons behave
SELECT typeof(reps) FROM workouts WHERE reps IS NOT NULL LIMIT 1;   -- integer
SELECT count(*) FROM workouts WHERE reps > 3;    -- no longer excludes '10'

-- nothing lost
SELECT count(*) FROM workouts;                    -- 9292
SELECT count(reps) FROM workouts;                 -- 9252
SELECT sum(reps) FROM workouts;                   -- compare to pre-migration
```

Capture `sum(reps)` and `count(reps)` before and after — equality proves no row
was truncated or nulled by the cast.

Tests touching reps as a string: `backend/tests/test_utils.py` (1RM cases,
including any asserting the `0.0` fallback — those assertions are now invalid and
should be replaced with a raising case), plus workout repository and progression
fixtures.

## 5. Rollback

`downgrade()` reverses the type via batch mode. Values round-trip exactly since
every integer renders as the same text it came from. No `+` is restored because
none existed.
