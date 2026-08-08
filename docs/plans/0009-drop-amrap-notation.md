# Plan 0009: Drop AMRAP notation — `reps` becomes an integer

**Status:** Proposed — **mostly implemented already by the `1a27a0b` merge**
**Prerequisites:** Plan 0002 (Alembic)
**Related:** ADR-0005
**Risk:** Low — verified lossless against production data

Small, self-contained, and worth doing early: it removes a silent-wrong-answer
class from every numeric query on `reps`, including the LLM-authored ones the
MCP server will run.

> **Revised after merge `1a27a0b`.** The remote had independently moved most of
> the way to this design — Wendler was replaced by a Liftoscript preset engine,
> and that parser already treats reps as integers with AMRAP as a comment. What
> remains is the database column and one error path.
>
> | Step | State |
> |---|---|
> | Pydantic `reps: int` on workout + upcoming | **Done** (`models/workout.py:16`, `models/upcoming.py:16`) |
> | `calculate_estimated_1rm(reps: int)`, string branch deleted | **Done** (`utils/calculations.py:4`) |
> | Generator stops emitting `"5+"` into `reps` | **Done** — see §3a |
> | `reps` column `String(16)` → `Integer` | **Outstanding** (`db/models.py:65,94`) |
> | Delete the `except → 0.0` fallback | **Outstanding** (`utils/calculations.py:15-23`) |
>
> This has produced a **type mismatch**: Pydantic declares `int` while the
> column is still `String(16)`. SQLite's dynamic typing masks it, so writes
> succeed and values come back as text — which is exactly the condition that
> makes `WHERE reps > 3` wrong. Closing it is now a consistency fix, not just a
> cleanup.

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

`workouts` also carries `ix_workouts_date_order` (`db/models.py:53`); confirm
indexes survive the rebuild, since batch mode recreates them from metadata.

## 3. Code changes

| File | Change | State |
|------|--------|-------|
| `backend/app/db/models.py:65,94` | `String(16)` → `Integer` on both `reps` columns | **Outstanding** |
| `backend/app/utils/calculations.py:15-23` | Delete the `try/except → 0.0` | **Outstanding** |
| `backend/app/services/liftoscript_service.py:70,191` | Capture `+` in `SET_PATTERN` instead of substring-scanning the spec | **Outstanding** — §3b |
| `backend/app/services/liftoscript_service.py:246-256` | Tag only the final set as AMRAP when `sets > 1` | **Outstanding** — §3b |
| `backend/app/models/workout.py:16` | `reps: Optional[int]` | Done |
| `backend/app/models/upcoming.py:16` | `reps: int \| None` | Done |
| `backend/app/utils/calculations.py:4` | Signature `reps: int`, string branch gone | Done |
| `backend/app/services/liftoscript_service.py:188-192` | Parses reps as `int` | Done |
| `frontend/src/types/workout.ts`, `upcoming.ts` | Confirm `reps: number` | Verify |

### `calculate_estimated_1rm`

The string branch is already gone. What remains (`utils/calculations.py:15-23`)
is the swallow:

```python
def calculate_estimated_1rm(weight: float, reps: int) -> float:
    try:
        reps_num = int(reps)
        weight_num = float(weight)
        estimated_1rm = (0.033 * reps_num * weight_num) + weight_num
        return round(estimated_1rm, 1)
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

## 3a. The generator already does this — via Liftoscript

`WEEK_PERCENTAGES` no longer exists. Merge `1a27a0b` replaced the hard-coded
Wendler table with a **Liftoscript preset engine**
(`services/liftoscript_service.py`, 296 lines; `wendler_service.py` is down to
64 and now only resolves 1RMs). Programmes live as text in
`backend/app/presets/*.liftoscript`.

AMRAP still exists **in the DSL**, which is the right place for it:

```
Barbell Squat / 1x5 65%, 1x5 75%, 1x5+ 85%
```

And the parser resolves it exactly as ADR-0005 prescribes
(`liftoscript_service.py:188-192`, `246-247`):

```python
sets = int(match.group(1))
reps = int(match.group(2))          # integer
is_amrap = "+" in sets_reps_str     # boolean flag
...
if is_amrap:
    comment_parts.append("AMRAP")   # prose, in the comment
```

**Integer reps, AMRAP as a comment.** The remote arrived at this independently,
which is a stronger endorsement of ADR-0005 than the ADR's own argument.

Two consequences:

- **No structural generator change is needed.** The parser is the right owner of
  AMRAP, and it already is.
- **The `+` survives where it belongs** — as programme notation in the
  `.liftoscript` source, not as a value in a numeric column. ADR-0005 worried
  that Wendler's AMRAP intent would be lost; it is not, it just lives in the
  preset text and the generated comment.

The lossless guarantee in §1 holds *going forward*, not just historically: the
only writer that could introduce `"5+"` into `reps` already writes an integer.

### 3b. Two parser defects to fix while we're here

Since the parser now owns AMRAP entirely, its detection should be exact.

**1. The `+` is matched but not captured.**

```python
SET_PATTERN = re.compile(r"(\d+)x(\d+)\+?")   # \+? consumed, never captured
...
is_amrap = "+" in sets_reps_str                # so it falls back to a substring scan
```

`sets_reps_str` is the **whole** spec — `"1x5+ 85%"` — not just the sets/reps
token. Detection therefore fires on a `+` anywhere in the string, including the
weight portion. Today's presets are all percentage-based so nothing triggers it,
but `1x5 BW+25lb` or any additive weight expression would be silently marked
AMRAP. Capture it instead:

```python
SET_PATTERN = re.compile(r"(\d+)x(\d+)(\+?)")
...
sets, reps = int(match.group(1)), int(match.group(2))
is_amrap = bool(match.group(3))
```

**2. AMRAP is applied to every set in a multi-set spec.**

```python
for _ in range(sets):
    workout = UpcomingWorkoutCreate(..., reps=reps, comment=comment)
```

`3x5+` would mark all three sets AMRAP. Convention — and Wendler specifically —
means the *last* set only. Latent today because every preset spec is `1x`
(`wendler_531.liftoscript` uses `1x5+`, `1x3+`, `1x1+` throughout), so `sets`
is always 1. It becomes a real bug the first time someone writes a multi-set
AMRAP in a custom preset.

Fix by tagging only the final iteration:

```python
for i in range(sets):
    last = i == sets - 1
    comment = "AMRAP" if (is_amrap and last) else None
```

Neither defect blocks the column migration. Both are cheap, and the first is
worth doing before custom presets exist to trip it.

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
