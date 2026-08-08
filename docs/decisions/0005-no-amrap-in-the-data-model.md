# ADR-0005: No AMRAP notation in the data model

**Status:** Accepted
**Date:** 2026-08-08

## Context

`workouts.reps` and `upcoming_workouts.reps` are `String(16)`
(`backend/app/db/models.py:64,93`) rather than integers, for one reason: to hold
AMRAP notation like `"5+"` — "five reps, then as many as possible".

That single affordance costs more than it returns:

- **`calculate_estimated_1rm`** (`backend/app/utils/calculations.py:4-28`)
  accepts `int | str`, strips `+`, and wraps the parse in a try/except that
  returns `0.0` on failure — a silent wrong answer rather than an error.
- **Sorting and comparison are lexicographic.** `WHERE reps > 3` matches `"10"`
  as *false*, because `"10" < "3"` as text. Any consumer writing the obvious
  query gets a wrong answer with no indication.
- **The MCP query tool makes this considerably worse** (ADR-0004). An LLM
  writing SQL against a column named `reps` will treat it as numeric. The
  workaround, `CAST(REPLACE(reps,'+','') AS INTEGER)`, has to be communicated
  and remembered on every query.
- **The `+` carries no quantity.** `"5+"` says a set went past five, not how far
  past. As data it is barely more informative than `5`, and it poisons the
  column's type for every row that doesn't use it.

Measured against the production copy (`data/helf.db`):

| | |
|---|---|
| `workouts` rows | 9,292 |
| Non-null `reps` | 9,252 |
| Containing `+` | **0** |
| Non-numeric | **0** |
| `upcoming_workouts` reps | only `5`, `10`, `6` |

**The notation is used by exactly nothing.** Eight years of history, zero AMRAP
rows. The column is typed as text to support a feature that has never produced a
single record, while degrading correctness for all 9,252 rows that exist.

## Decision

**`reps` becomes an integer. AMRAP notation is removed from the data model.**

1. `workouts.reps` and `upcoming_workouts.reps` become `Integer`, nullable.
2. `calculate_estimated_1rm` takes `int`. The string branch and the
   `except: return 0.0` are deleted — a bad input should raise, not silently
   yield zero.
3. **The Wendler generator stops emitting `+`.**
   `backend/app/services/wendler_service.py:44-49` currently produces `'5+'`,
   `'3+'`, `'1+'` for the top set of weeks 1–3. Those become `5`, `3`, `1`.
4. If the "go past this number" intent matters on a given set, it belongs in the
   existing `comment` field as prose. It is a note, not a measurement.

## Consequences

- **Numeric comparison works.** `WHERE reps > 3`, `ORDER BY reps`, `AVG(reps)`
  all behave correctly — for the app, and for LLM-authored SQL, which is where
  the text type was most dangerous because the failure is silent.
- **The 1RM calculation loses its silent-failure path.** Today a malformed
  `reps` yields an estimated 1RM of `0.0`, which flows into charts as a real
  data point. After this it raises.
- **Migration is lossless**, uniquely so: zero rows contain `+` and zero are
  non-numeric, so `CAST` is exact for every existing row. This will not be true
  later if AMRAP ever starts being recorded — which is an argument for doing it
  now rather than deferring.
- **The prescriptive top set loses its "+" marker.** Wendler's 5/3/1 does
  intend the last set as AMRAP, and that intent is no longer expressed in the
  data. It survives as programme knowledge and can be written into `comment`.
  This is the real cost of the decision, and it is accepted: the marker was
  never recorded as an outcome, only as an instruction.
- **One fewer thing in the MCP instructions.** The `CAST(REPLACE(...))` caveat —
  flagged in `plans/0006-mcp-server.md` §5 as the single most important line —
  disappears entirely.
