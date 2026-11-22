# 0020 — Hand-built presets

**Status**: Implemented 2026-11-22 · `ef7567caec16`

A preset is a workout built once, tile by tile, and applied to any day. The
Workouts section's second tab lists them; **Add preset** opens one on the day
editor.

## 1. What a preset is, and is not

- **Is:** a named list of planned set tiles — the same targets a planned
  `workouts` row carries (exercise, weight, reps, distance, timing, comment,
  the mobility flag), in order.
- **Is not:** a Liftoscript preset. Those (`app/presets/*.liftoscript`, served
  at `/api/upcoming/presets`) are program *templates* that generate the
  upcoming queue. The two share a word and nothing else; the code keeps them
  apart by name (`presetsApi` / `useWorkoutPreset*` vs `upcomingApi.getPresets`
  / `usePresets`).
- **Is not history.** Applying a preset writes ordinary planned workout rows,
  and nothing points back. Editing or deleting a preset never changes a day it
  was applied to — the stack argument (0011 §2), for the same reason.

## 2. Storage

Two tables, added by `ef7567caec16` and touching nothing else:

- `workout_preset` — `name` (unique, never blank), timestamps.
- `workout_preset_item` — one row per tile: `preset_id` (cascade), exercise,
  category, `order`, and exactly the target columns of `workouts`, with the
  same CHECKs. No completion, no actuals: a preset is never performed.

Rejected:

- **`upcoming_workouts` with a preset key.** That table is the queue, which the
  Liftoscript generator clears wholesale (0019). A preset must survive it.
- **`workouts` under a sentinel date.** Those rows are history — audited,
  counted by the calendar and `v_daily_summary`, read by the agent.

**Not audited**, matching `upcoming_workouts` and `mobility_plan`: a plan that
has not been run is not history. Applying is the moment it becomes some, as
audited workout rows.

## 3. One editor, two stores

The day view's editor — add form, cards, inline edit, drag reorder, delete —
is `DayEditor` in `pages/WorkoutSession.tsx`, fed a **tile source**
(`hooks/useTileSource.ts`): a dated day (`useDayTileSource`, the existing
workout hooks) or a preset (`usePresetTileSource`). Preset items are handed to
the editor in the `Workout` shape as planned tiles, so the card cannot tell
them apart. The inline edit form writes through the source from context.

Rendered only for a day: completion, the day player, Move, Copy, the bulk
mobility flag, the movement break suggestion. A preset keeps the per-set
mobility toggle — whether a set is mobility work is part of the plan, and it
travels to the day.

The alternative was a separate preset page reusing the pieces; rejected
because two editors drift, and this one already carries a lot of hard-won
behaviour (memoised cards, stable drag listeners, field configuration).

## 4. Making and applying

- **Add preset** creates one immediately, named "New preset" (numbered if
  taken), and opens it with the name selected to type over. There is no
  separate naming step, and no Save for tiles — they save as they change, as
  on a day. An abandoned preset stays in the list until deleted.
- The field-configuration guard (0018) applies to preset tiles too: a group
  the exercise has disabled is nulled on write.
- **Apply to day** copies every tile onto the chosen date as **planned**
  rows, appended after whatever the day holds, then opens that day. Usage
  (`exercises.last_used`) does not move — it moves at performance (0018).
  An empty preset cannot be applied (422; the button is hidden).

## 5. API (`/api/presets`)

`GET /`, `POST /` (name optional), `GET|PUT|DELETE /{id}`,
`POST /{id}/items`, `PUT|DELETE /items/{item_id}`, `PATCH /{id}/reorder`,
`POST /{id}/apply`. Not exposed over MCP: the agent has no use for it yet.
