# 0021 — Liftoscript timing and distance

**Status**: Implemented 2026-11-22 · `842c1976c18a`

Plan 0018 gave set tiles target timing (work per rep, rest between reps,
rest after the set) and made distance a configurable group. The program
editor could not write any of it: the parser read sets × reps, weight and
`lp()` only, and anything else on a line was silently ignored. This adds the
syntax, and the queue columns to carry it to the day.

## 1. Syntax

After the `NxM` of a set spec, in any order:

| Token | Meaning | Spellings |
|---|---|---|
| a duration | work per rep | `10s`, `90sec`, `2min`, `1:30` |
| `rest` + duration | rest between reps | `rest 5s` |
| `after` + duration | rest after the set (the divider) | `after 30s` |
| number + unit | distance | `400m`, `5km`, `1.5mi`, `100yd` |

```
Plank / 3x6 10s rest 5s after 30s
Farmer Carry / 1x2 70lb 40s rest 20s
Rower / 1x1 2000m
Run / 1x1 800m 4min
```

- **Keywords, not commas.** Commas already separate set specs
  (`1x5 65%, 1x3 80%`), so the rest-after cannot follow one.
- **`m` is metres.** Minutes are always `min` or `m:ss`, so `5m` can never be
  read two ways.
- `rest` and `after` are taken out before the work time is looked for:
  `rest 5s` is never five seconds of work.
- Bounds are the tile's CHECKs (work 1s–60min, rests 0–60min); out of range is
  a parse error naming the exercise.
- Existing scripts parse exactly as before.

## 2. The queue carries it

`upcoming_workouts` gains `work_seconds`, `rest_seconds`, `rest_after_seconds`
with the same named CHECKs as `workouts` (plain `ADD COLUMN`s; the downgrade
is plain `DROP COLUMN`s — a batch rebuild would hoist `ck_upcoming_is_mobility`
to table level and break 9c4e7b21f806's own downgrade). Transfer copies them
field for field; the legacy `time` string is still promoted to `work_seconds`
when a row has nothing else. Distance already had columns.

## 3. Field configuration is not allowed to eat it

Transfer creates the day's sets through the workout repository, which nulls
any group the exercise has disabled (0018). Unchecked, a scripted `30s` on an
exercise with Time off would vanish between the queue and the day. So:

- **An exercise the program creates** is created with the groups it uses
  turned on.
- **An existing exercise with the group off** makes generate refuse the whole
  program — before the queue is cleared — naming the exercise and the fix.
  Exercises are never reconfigured behind the user's back.

## 4. Found on the way: categories

The parser knows about eighteen lifts' categories and labels the rest
"Other", which then landed on the queued set and the logged one. A movement
already in the catalog now keeps its own category; only a new one takes the
parser's guess.

## 5. Not done

- The agent's `write_next_mobility_session` tool still writes sets without
  timing; its columns are nullable and it is unaffected.
- RPE (`@8`) has a pattern in the parser and still no column.
