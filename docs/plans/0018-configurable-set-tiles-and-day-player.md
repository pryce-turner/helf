# 0018 — Configurable set tiles and the day player

**Status:** Implemented 2026-11-19, through `85ac045`

The interval timer is gone as a separate tool. The day view's rows are now
**set tiles** — each holding *targets* beside *actual performance* — and a
**day player** executes the day's incomplete tiles in order, records what was
actually performed, and invents nothing.

The mapping from the old timer, which this plan supersedes:

| Old timer concept | New day-view concept |
|---|---|
| Work + rest | One rep |
| Exercises | Reps in a set |
| Round | One set tile |
| Round reset | Rest divider after the preceding set tile |
| Optional run weight | Nullable weight field on the set tile |
| Start / Pause / Stop | Day-level Play / Pause / Stop |
| Movement-break shuffle | Insert a suggested, incomplete mobility set tile |

## 1. Exercise-driven field configuration

Every exercise carries four independently enabled field groups with nullable
defaults: **Reps** (`default_reps`), **Weight** (`default_weight_lb`, total
pounds — for a Farmer Carry, across both hands), **Distance**
(`default_distance` + `default_distance_unit`), and **Time**
(`default_work_seconds`, `default_rest_seconds`,
`default_rest_after_seconds`). Enabled with a NULL default offers the input
blank; disabled offers nothing. **Defaults are snapshots**: they apply at tile
creation, and editing the exercise afterwards never rewrites a tile or
history. A disabled group keeps its defaults stored, so re-enabling restores
the configuration rather than a blank one.

`movement_break_seconds` became `movement_break_enabled` plus the ordinary
time defaults — pool membership and the default bout were one nullable number,
and the bout is timing configuration like any other. The migration
(`a3f9c21d7e48`) backfills: pool members keep their bout as
`default_work_seconds` with `default_reps = 2` and
`default_rest_seconds = min(30, max(10, round(work / 2)))` (the timer's own
formula); Time and Distance enable where history exists; Reps and Weight stay
enabled everywhere, preserving the editor as it was. Every bound is a named
CHECK (`ck_exercises_default_*`).

## 2. Set tiles: targets beside actuals

`workouts` (`b7e2d4f81a05`) gains target timing (`work_seconds`,
`rest_seconds`, `rest_after_seconds`) and actual performance
(`completed_reps`, `actual_work_seconds`, `actual_rest_seconds`,
`actual_rest_after_seconds` — REAL, a partial rep measures in wall-clock
seconds — and `ended_early`). A tile is planned (`completed_at IS NULL`,
actuals NULL) or performed.

- `POST /api/workouts/{id}/perform` writes the player's measurement. Natural
  completion derives the full actuals **as totals** (`work_seconds × reps`;
  the per-rep rest runs `reps − 1` times, never after the last rep) — but an
  explicitly sent value wins per field, because the player's snapshot is
  immutable and a tile edited mid-run must be written as it was at Play. The
  server assigns `completed_at` **and the date**: work is logged the day it
  is performed, so a tile played from another day's view moves to today.
- `PATCH /api/workouts/{id}/rest-after` records the divider alone (409 on a
  tile not performed), so a Stop mid-rest completes no next tile.
- The manual tick derives actuals from targets and clears them on untick.
  Copies reset performance and keep targets. `update` treats `completed_at`
  as sticky-unless-sent (the `is_mobility` rule), so a comment edit can no
  longer uncomplete a set — that was a latent bug the old shape hid.
- `last_used` / `use_count` move at **performance**, not suggestion.
- The calendar, the progression history, and `v_daily_summary` count
  performed tiles only; volume uses `COALESCE(completed_reps, reps)`.

Backfill: completed rows gain `completed_reps = reps`; a plain `m:ss` `time`
parses into `work_seconds`, and into `actual_work_seconds` for completed
rows. Movement-break history stays as separate timed sets — no rest or round
structure is invented for it, and **it cannot be faithfully regrouped**: the
old rows lack rest and round information. `time` is kept as read-only legacy
and drops in a follow-up, so there is never two writable representations.

## 3. The suggestion, not the finished run

`POST /api/mobility/suggest` replaced `POST /api/mobility/movement-break`.
The old writer created one completed row per interval — the only shape the
schema had. The new one inserts an ordinary planned tile holding the
shuffled movement's defaults (`is_mobility` set), appended at the day's end.
The three-candidates-least-recently-used shuffle moved server-side with it,
reading a `last_used` that now moves only at performance — an unused
suggestion cannot make a movement look done, and it is editable and
deletable like any planned tile. Buttons disable while the write is in
flight; a double tap must not insert two.

## 4. The day player

`useWorkoutPlayer` builds a phase list from an immutable snapshot: one
get-ready, then per tile its work reps with per-rep rests (never after the
last rep), a manual wait for untimed tiles, and the rest-after divider
between tiles — never after the last. A tile's performance writes **before**
the run advances, from the snapshot; a failed write halts with Retry, which
repeats the snapshot byte for byte. Pause banks the remainder; paused wall
time reaches no actual. Stop writes measured actuals with `ended_early`, or
only the partial rest-after on the preceding tile, or nothing (get-ready,
manual wait). A stopped tile stays completed — replay starts at the first
incomplete tile. The active tile locks and glows.

The timing engine is the old timer's (absolute deadlines, overshoot carried,
cues, wake lock); the page and its route are gone, `/timer` redirects to
today.

## 5. No rest rows, no interval summary

Rest-after lives **on the preceding tile** and renders as a divider. The
alternative — a rest exercise, or a second row type with nullable
exercise/category keys — was rejected: it preserves the flat set model, the
foreign keys, the counts, the ordering and the audit semantics while still
giving rest a visible, playable form. The earlier interval-session summary
table was dropped from the design for the same reason: the tiles and their
actuals already say everything it would have.

## 6. Verification

- `backend/tests/test_migration_field_config.py` and
  `test_migration_set_tiles.py` upgrade seeded pre-0018 databases and
  round-trip them (downgrade restores the old shape byte-for-byte, including
  the view SQL).
- `alembic check` clean; full `downgrade base && upgrade head` round trip on
  a scratch `DATA_DIR`.
- The perform/rest-after contracts, derive-and-clear on the tick, copy
  resets, performed-only counts (calendar, progression, `v_daily_summary`),
  and the snapshot-over-edit rule are covered in
  `test_repositories_workout.py` / `test_api_workouts.py`.
- The player is covered pure (`workoutPlayer.test.ts`), headless
  (`useWorkoutPlayer.test.tsx`, fake timers — pause/resume, Stop mid-work /
  mid-rest / mid-divider / get-ready, manual waits, one write per tile,
  failed-write Retry), and mounted (`WorkoutSession.test.tsx`).

Two environment caveats recorded during the work: `test_pre_migration_hook.py`
fails here for want of a `sqlite3` CLI (pre-existing, unrelated), and the
production migration has **not** been run in this checkout — it needs the
prescribed `scripts/backup-db.sh` first, per the README's own rule.
