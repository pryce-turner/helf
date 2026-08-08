# Liftoscript-Based Upcoming Workouts

## Overview

Transform the Upcoming Workouts page from a Wendler-specific generator to a flexible Liftoscript-based program editor. Users will write/edit programs in a text editor using Liftoscript syntax, then generate upcoming workout sessions.

**Reference**: [Liftoscript Documentation](https://www.liftosaur.com/docs)

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Editor Type | Plain textarea | Faster to implement, functional for MVP |
| Warning Dialog | Only when workouts exist | Less annoying UX when list is empty |
| Cycles Support | Multiple cycles with input | Preserves current Wendler functionality |
| Migration | Replace Wendler dialog entirely | Cleaner UI, Liftoscript is more flexible |

---

## Architecture Changes

### Backend

#### New Files

1. **`backend/app/services/liftoscript_service.py`** - Liftoscript Parser Service
   - Parse Liftoscript syntax into workout objects
   - Accept 1RM values for percentage calculations
   - Return list of `UpcomingWorkoutCreate` objects

2. **`backend/app/presets/wendler_531.liftoscript`** - Wendler 5/3/1 Preset
   - Full 4-week cycle template in Liftoscript format
   - Parameterized for multiple cycles

#### Modified Files

1. **`backend/app/api/upcoming.py`** - New endpoints
2. **`backend/app/models/upcoming.py`** - New Pydantic models
3. **`backend/app/repositories/upcoming_repo.py`** - Add `delete_all()` method

### Frontend

#### New Files

1. **`frontend/src/components/LiftoscriptEditor.tsx`** - Editor component
2. **`frontend/src/components/PresetSelector.tsx`** - Preset dropdown + 1RM inputs

#### Modified Files

1. **`frontend/src/pages/Upcoming.tsx`** - Major refactor
2. **`frontend/src/hooks/useUpcoming.ts`** - New hooks
3. **`frontend/src/lib/api.ts`** - New API endpoints
4. **`frontend/src/types/upcoming.ts`** - New TypeScript types

---

## Liftoscript Parser Scope

### Supported Features (MVP)

| Feature | Syntax Example | Notes |
|---------|----------------|-------|
| Exercise declaration | `Bench Press / 3x8` | Exercise name + sets x reps |
| Weight in lbs | `60lb` | Absolute weight |
| Weight in kg | `60kg` | Converts to lbs internally |
| Percentage of 1RM | `80%` | Requires 1RM input |
| Week headers | `# Week 1` | Groups by week |
| Day headers | `## Day 1` or `## Squat Day` | Groups by day/session |
| Multiple sets | `1x5, 1x3, 1x1` | Different reps per set |
| Rep ranges | `3x8-12` | Min-max reps |
| AMRAP | `5+` | Stored as "5+" in reps field |
| Comments | `// description` | Stored in workout comment |

### Not Supported (Future Enhancement)

- RPE notation: `@8`
- Progression scripts: `progress: lp(5lb)`
- Update scripts: `update: custom()`
- Timers: `60s`
- Warmups: `warmup: ...`
- Supersets: `superset: A`
- Reuse syntax: `...Squat`
- Templates: `used: none`

---

## API Endpoints

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upcoming/liftoscript/generate` | Parse script, clear existing, create workouts |
| GET | `/api/upcoming/presets` | List available presets |
| GET | `/api/upcoming/presets/{name}` | Get preset content |

### Existing Endpoints (Keep)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/upcoming/wendler/maxes` | Get auto-detected 1RM values |
| GET | `/api/upcoming/` | List all upcoming workouts |
| DELETE | `/api/upcoming/session/{session}` | Delete session |
| POST | `/api/upcoming/session/{session}/transfer` | Transfer to historical |

### Removed Endpoints

| Method | Path | Reason |
|--------|------|--------|
| POST | `/api/upcoming/wendler/generate` | Replaced by Liftoscript generate |

---

## Pydantic Models

### New Models

```python
class LiftoscriptGenerateRequest(BaseModel):
    script: str                         # Liftoscript program text
    squat_max: Optional[float] = None   # 1RM override for squat
    bench_max: Optional[float] = None   # 1RM override for bench
    deadlift_max: Optional[float] = None # 1RM override for deadlift
    num_cycles: int = 1                 # Number of cycles (for presets)

class LiftoscriptGenerateResponse(BaseModel):
    success: bool
    message: str
    count: int                          # Workouts created
    sessions: int                       # Sessions created
    deleted_count: int                  # Existing workouts deleted

class PresetInfo(BaseModel):
    name: str                           # e.g., "wendler_531"
    display_name: str                   # e.g., "Wendler 5/3/1"
    description: str
    requires_maxes: bool                # True if uses percentage notation

class PresetContent(BaseModel):
    name: str
    display_name: str
    script: str                         # Full Liftoscript text
```

---

## Wendler 5/3/1 Preset Format

The current Python-based Wendler generator will be converted to Liftoscript format:

```liftoscript
# Week 1
## Squat Day
// Main Lift - 5/5/5+ Week
Barbell Squat / 1x5 65%, 1x5 75%, 1x5+ 85%
// Accessories
Pull Up / 3x8
Incline Dumbbell Press / 3x10
Decline Crunch / 3x15

## Bench Day
// Main Lift - 5/5/5+ Week
Flat Barbell Bench Press / 1x5 65%, 1x5 75%, 1x5+ 85%
// Accessories
Front Squat / 3x8
Dumbbell Row / 3x10
Landmines / 3x12

## Deadlift Day
// Main Lift - 5/5/5+ Week
Deadlift / 1x5 65%, 1x5 75%, 1x5+ 85%
// Accessories
Parallel Bar Triceps Dip / 3x8
Bulgarian Split Squat / 3x10
Cable side bend / 3x15

# Week 2
## Squat Day
// Main Lift - 3/3/3+ Week
Barbell Squat / 1x3 70%, 1x3 80%, 1x3+ 90%
...

# Week 3
## Squat Day
// Main Lift - 5/3/1+ Week
Barbell Squat / 1x5 75%, 1x3 85%, 1x1+ 95%
...

# Week 4
## Squat Day
// Deload Week
Barbell Squat / 1x5 40%, 1x5 50%, 1x5 60%
...
```

### Multi-Cycle Generation

When `num_cycles > 1`, the parser will:
1. Repeat the 4-week template N times
2. Apply progressive overload per cycle:
   - Squat/Deadlift: +10lb per cycle to 1RM
   - Bench: +5lb per cycle to 1RM
3. Generate session numbers sequentially

---

## UI Flow

```
+------------------------------------------------------------+
| UPCOMING WORKOUTS                                          |
| Plan and manage your future training sessions              |
|                                          [Edit Program]    |
+------------------------------------------------------------+
|                                                            |
| +- PROGRAM EDITOR --------------------------------------- +|
| |                                                        | |
| | Preset: [Wendler 5/3/1 v]    Cycles: [4]              | |
| |                                                        | |
| | +- 1RM Overrides ------------------------------------+ | |
| | | Squat: [315] lbs   Bench: [225] lbs   DL: [365] lbs| | |
| | | (Auto-detected from workout history)               | | |
| | +----------------------------------------------------+ | |
| |                                                        | |
| | +----------------------------------------------------+ | |
| | | # Week 1                                           | | |
| | | ## Squat Day                                       | | |
| | | // Main Lift - 5/5/5+ Week                         | | |
| | | Barbell Squat / 1x5 65%, 1x5 75%, 1x5+ 85%        | | |
| | | // Accessories                                     | | |
| | | Pull Up / 3x8                                      | | |
| | | ...                                                | | |
| | +----------------------------------------------------+ | |
| |                                                        | |
| |                              [Cancel]  [Generate]      | |
| +--------------------------------------------------------+ |
|                                                            |
| +- SESSION 1 ---------------------------------------------+|
| | 6 exercises planned          [Transfer] [Delete]       | |
| | +-----------------------------------------------------+| |
| | | 1  Barbell Squat     [Legs]  205 lbs  5 reps        || |
| | |    Week 1 - Set 1                                   || |
| | +-----------------------------------------------------+| |
| | ...                                                    | |
| +---------------------------------------------------------+|
|                                                            |
+------------------------------------------------------------+
```

---

## Confirmation Dialog

When "Generate" is clicked and existing workouts exist:

```
+------------------------------------------------+
| Overwrite Upcoming Workouts?                   |
+------------------------------------------------+
|                                                |
| This will delete all 48 existing upcoming      |
| workouts and generate new ones from your       |
| program.                                       |
|                                                |
| This action cannot be undone.                  |
|                                                |
|                    [Cancel]  [Generate]        |
+------------------------------------------------+
```

---

## Implementation Tasks

### Backend Tasks (Build Agent)

| # | Task | File(s) | Complexity |
|---|------|---------|------------|
| B1 | Create Liftoscript parser service | `services/liftoscript_service.py` | High |
| B2 | Add preset file storage | `presets/wendler_531.liftoscript` | Low |
| B3 | Add Pydantic models | `models/upcoming.py` | Low |
| B4 | Add `delete_all()` repository method | `repositories/upcoming_repo.py` | Low |
| B5 | Add new API endpoints | `api/upcoming.py` | Medium |
| B6 | Remove old Wendler generate endpoint | `api/upcoming.py` | Low |

### Frontend Tasks (Frontend-Polish-Expert)

| # | Task | File(s) | Complexity |
|---|------|---------|------------|
| F1 | Create LiftoscriptEditor component | `components/LiftoscriptEditor.tsx` | Medium |
| F2 | Create PresetSelector component | `components/PresetSelector.tsx` | Medium |
| F3 | Refactor Upcoming.tsx page | `pages/Upcoming.tsx` | Medium |
| F4 | Add confirmation dialog | `pages/Upcoming.tsx` | Low |
| F5 | Add hooks and API client | `hooks/useUpcoming.ts`, `lib/api.ts`, `types/upcoming.ts` | Low |

---

## Execution Order

1. **Backend first** - Parser service + models + endpoints
2. **Frontend second** - Components + page refactor (depends on backend API)

---

## Testing Checklist

### Backend
- [ ] Parser handles basic `Exercise / SETSxREPS` syntax
- [ ] Parser handles weight formats: `60lb`, `60kg`, `80%`
- [ ] Parser handles week/day headers
- [ ] Parser handles multiple sets and rep ranges
- [ ] Parser handles AMRAP notation `5+`
- [ ] Parser handles comments `// description`
- [ ] Percentage calculations use provided 1RM values
- [ ] Generate endpoint clears existing workouts
- [ ] Presets endpoint returns correct data

### Frontend
- [ ] Preset selector populates editor
- [ ] 1RM inputs auto-populate from detected maxes
- [ ] Generate button calls API correctly
- [ ] Confirmation dialog shows correct count
- [ ] Sessions display after generation
- [ ] Error handling for invalid scripts

---

## Future Enhancements

1. **Syntax highlighting** in editor
2. **Live preview** of parsed workouts
3. **More presets**: Starting Strength, nSuns, PPL templates
4. **RPE support** in parser
5. **Progressive overload scripts** support
6. **Import/Export** programs as files
7. **Program library** with community-shared programs
