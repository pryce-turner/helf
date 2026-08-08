# Liftoscript Refactoring Plan

## Final Plan

### Summary of Decisions

- **1RM Endpoint**: Keep `/wendler/maxes` for display purposes
- **Cycles**: Keep `num_cycles` to repeat the script N times
- **Percentages**: Require 1RM inputs when script contains `%` notation
- **Categories**: Validate that all exercises exist in the database with a category; error if not found

---

## Backend Changes

### 1. Simplify liftoscript_service.py

#### Remove:
- Week/day header parsing (`# Week 1, ## Squat Day`) - sessions will be determined differently
- Comment parsing (`//`)
- Automatic category inference from exercise names
- Progressive overload per cycle (incrementing 1RMs)
- `_round_weight()` logic (user provides exact weights or percentages)

#### Keep/Modify:
- Basic parsing: exercise name, sets×reps, weights
- AMRAP notation (`5+`), rep ranges (`8-12`)
- Multiple set definitions (`1x5, 1x3, 1x1`)
- Percentage parsing (`80%`) → convert to weight only if 1RM provided
- Absolute weights (`60lb, 60kg`) → convert kg to lbs
- Equipment variants (`Bench Press, Dumbbell`)
- Cycles parameter (repeat entire script N times)
- RPE notation (`@8`) - store as metadata
- Rest time (`20s`) - store as metadata

#### New:
- Validate exercises exist in database before generating
- Look up category from exercise database
- Error with helpful message listing unknown exercises
- Session numbering: increment session after a blank line (or use explicit markers)

### 2. Update wendler_service.py

#### Keep only:
- `get_current_maxes()` method for 1RM detection
- `get_latest_estimated_1rm()` helper

#### Remove:
- `generate_progression()`
- `generate_and_save()`
- `calculate_weights()`
- All constants (`MAIN_LIFTS, ACCESSORIES, WEEK_PERCENTAGES`)

---

## API Changes

### 3. Update upcoming.py API

- Keep `get_wendler_current_maxes` endpoint (for display)
- Keep `generate_liftoscript_workouts` endpoint
- Keep `LiftoscriptGenerateRequest` with 1RM fields (used only when script has `%`)
- Presets remain simple - just load and return string content

### 4. Update models/upcoming.py

- Remove `WendlerGenerateRequest` and `WendlerGenerateResponse` (unused)
- Keep `LiftoscriptGenerateRequest` with optional 1RM fields
- Keep `WendlerCurrentMaxes` for the display endpoint

---

## Frontend Changes

### 1. Update Upcoming.tsx

- Keep 1RM input fields but only show them when preset has `requires_maxes: true` OR when the script content contains `%`
- Dynamically detect if script contains `%` to show/hide 1RM fields
- Keep cycles input

### 2. Keep hooks and API methods

- `useWendlerMaxes` stays (for populating 1RM defaults)
- `useLiftoscriptGenerate` stays
- API methods stay

### 3. Update preset metadata

- `requires_maxes` can be removed from PRESETS dict (or kept for explicit presets)
- Frontend can auto-detect by checking if script contains `%`

---

## File Changes Summary

| File | Action |
|------|--------|
| `backend/app/services/liftoscript_service.py` | Major rewrite - simplify parser, add exercise validation |
| `backend/app/services/wendler_service.py` | Strip to only `get_current_maxes()` |
| `backend/app/api/upcoming.py` | Remove Wendler generation code, keep maxes endpoint |
| `backend/app/models/upcoming.py` | Remove unused Wendler models |
| `backend/app/presets/wendler_531.liftoscript` | Keep as-is (it's already in liftoscript format) |
| `backend/tests/test_services_wendler.py` | Update or remove |
| `backend/tests/test_api_upcoming.py` | Update tests |
| `frontend/src/pages/Upcoming.tsx` | Auto-detect `%` in script to show 1RM fields |
| `frontend/src/types/upcoming.ts` | Minor cleanup |