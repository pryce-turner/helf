# Helf - Health & Fitness Tracker

> ## Start here
>
> **[`docs/plans/README.md`](docs/plans/README.md) is the entry point for any
> session doing schema or integration work.** It carries the status of every
> plan, what is left in each, the commands that report current state, and a
> list of things a cold session reliably gets wrong. Read it before opening an
> individual plan.
>
> Two conventions that matter more than they look:
>
> - **The plans predate the schema.** Several were written against a shape that
>   has since changed. Re-derive against the live database before implementing
>   one, and when the data contradicts the plan, trust the data and fix the
>   plan. `docs/plans/0008-bodyspec-integration.md` §12 is the worked example.
> - **`data/helf.db` is a live copy of production.** WAL is on, so `cp` is not
>   a consistent copy — use `scripts/backup-db.sh`, which wraps
>   `sqlite3 … ".backup …"` and verifies what it wrote. **Back up before every
>   migration, and keep every backup** — see
>   [Backups](#backups-and-why-none-are-deleted). Nothing in `data/` is pruned
>   or overwritten.
>
> Settled decisions live in [`docs/decisions/`](docs/decisions/) as ADRs. They
> record *why*, and are not to be re-litigated without new evidence.

## Project Overview

Helf is a modern Progressive Web App (PWA) for tracking workouts, monitoring body composition, and planning training sessions. Refactored from a NiceGUI monolith to a FastAPI + React architecture.

**Status**: Production Ready (v2.0.0)

## Tech Stack

### Backend
- **Framework**: FastAPI 0.127+
- **Database**: SQLite + SQLAlchemy 2.x
- **MQTT**: Paho-MQTT 2.1+ — **retired fallback** (plan 0015), off unless `MQTT_ENABLED=true`
- **Validation**: Pydantic v2
- **Server**: Uvicorn with multi-worker support
- **Package Manager**: UV (with pyproject.toml)
- **Python**: 3.11+

### Frontend
- **Framework**: React 19+ with TypeScript 5.9+
- **Build Tool**: Vite 7+
- **UI Components**: shadcn/ui (Radix UI + Tailwind)
- **Styling**: Tailwind CSS 4+
- **State Management**: TanStack Query (React Query) v5
- **Routing**: React Router v7
- **Charts**: Recharts 3.6+
- **Drag-and-Drop**: dnd-kit
- **Icons**: Lucide React
- **Date Handling**: date-fns 4+

### PWA
- **Plugin**: vite-plugin-pwa
- **Caching**: Workbox (cache-first assets, network-first API)
- **Features**: Offline support, installable, service worker with auto-update

## Project Structure

```
helf/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   │   ├── workouts.py
│   │   │   ├── exercises.py
│   │   │   ├── progression.py
│   │   │   ├── upcoming.py
│   │   │   ├── mobility.py
│   │   │   ├── body_comp.py
│   │   │   ├── food.py
│   │   │   ├── notes.py
│   │   │   └── stacks.py
│   │   ├── db/
│   │   │   └── models.py     # SQLAlchemy ORM models (tables)
│   │   │                     #   No BodyComposition — retired by plan 0010;
│   │   │                     #   measurements are Observation + Metric
│   │   ├── models/           # Pydantic request/response schemas
│   │   │   ├── workout.py
│   │   │   ├── exercise.py
│   │   │   ├── progression.py
│   │   │   ├── upcoming.py
│   │   │   ├── mobility.py
│   │   │   ├── body_composition.py
│   │   │   ├── food.py
│   │   │   ├── note.py
│   │   │   └── stack.py
│   │   ├── repositories/     # SQLAlchemy data access layer
│   │   │   ├── workout_repo.py
│   │   │   ├── exercise_repo.py
│   │   │   ├── upcoming_repo.py   # kind-scoped: lifting vs mobility
│   │   │   ├── mobility_repo.py
│   │   │   ├── body_comp_repo.py
│   │   │   ├── food_repo.py
│   │   │   ├── note_repo.py
│   │   │   └── stack_repo.py
│   │   ├── services/         # Business logic
│   │   │   ├── progression_service.py
│   │   │   ├── mqtt_service.py   # retired ingest, kept as a fallback (0015)
│   │   │   ├── wendler_service.py
│   │   │   ├── mobility_service.py
│   │   │   └── liftoscript_service.py
│   │   ├── utils/            # Helper functions
│   │   │   ├── calculations.py   # 1RM estimation, moving averages
│   │   │   └── date_helpers.py   # Timezone, date parsing/formatting
│   │   ├── presets/          # Built-in workout programs
│   │   │   ├── wendler_531.liftoscript
│   │   │   └── stronglifts_5x5.liftoscript
│   │   ├── mcp/
│   │   │   └── qs_mcp.py     # Stdio MCP server (read-only by default)
│   │   ├── config.py         # Pydantic BaseSettings (env vars)
│   │   ├── database.py       # SQLAlchemy engine/session, pragmas, init_db
│   │   └── main.py           # FastAPI app, lifespan, CORS, SPA routing
│   ├── migrations/
│   │   ├── alembic/          # Alembic migration environment
│   │   │   ├── env.py        # Wired to app settings + Base.metadata
│   │   │   └── versions/     # Revision scripts
│   │   ├── tinydb_to_sqlite.py   # Legacy one-shot data import
│   │   └── import_mobility_pool.py   # One-shot Overview.md → exercises
│   ├── alembic.ini
│   ├── tests/                # 18 pytest test files
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Navigation.tsx         # Desktop sidebar + mobile bottom bar
│   │   │   ├── SectionTabs.tsx        # Sibling routes sharing one nav entry
│   │   │   ├── BodySectionTabs.tsx    # Composition + Food (ADR-0006)
│   │   │   ├── TrainingSectionTabs.tsx # Lifting + Mobility
│   │   │   ├── LiftoscriptEditor.tsx  # Script editor for workout programs
│   │   │   ├── PresetSelector.tsx     # Dropdown for built-in presets
│   │   │   ├── PWA/
│   │   │   │   └── InstallPrompt.tsx  # Add to Home Screen prompt
│   │   │   └── ui/                    # shadcn/ui primitives
│   │   │       ├── button.tsx, card.tsx, input.tsx
│   │   │       ├── label.tsx, select.tsx, calendar.tsx
│   │   ├── hooks/            # Custom React Query hooks
│   │   │   ├── useWorkouts.ts         # CRUD, calendar, reorder, move/copy
│   │   │   ├── useExercises.ts        # CRUD, categories, seed
│   │   │   ├── useProgression.ts      # 1RM data, main lifts
│   │   │   ├── useBodyComposition.ts  # Measurements, trends, stats
│   │   │   ├── useUpcoming.ts         # Sessions, Liftoscript, presets
│   │   │   ├── useMobility.ts         # Pending session, transfer, discard
│   │   │   ├── useFood.ts             # Day, summary, catalog search, logging
│   │   │   ├── useStacks.ts           # Preset groups, one-tap logging
│   │   │   └── usePWA.ts             # Online status, install prompt
│   │   ├── lib/
│   │   │   └── api.ts        # Axios instance + all API functions
│   │   ├── pages/
│   │   │   ├── Calendar.tsx           # Month view + streak
│   │   │   ├── WorkoutSession.tsx     # Day view, log exercises
│   │   │   ├── Progression.tsx        # 1RM charts
│   │   │   ├── Upcoming.tsx           # Session planner + Liftoscript
│   │   │   ├── Mobility.tsx           # Next mobility session, agent-written
│   │   │   ├── BodyComposition.tsx    # Trends + stats
│   │   │   ├── Food.tsx               # Daily log vs measured kcal target
│   │   │   ├── Supplements.tsx        # Stacks, logged in one tap, and the dose log
│   │   │   └── Exercises.tsx          # Exercise catalog
│   │   ├── types/            # TypeScript type definitions
│   │   │   ├── workout.ts, exercise.ts
│   │   │   ├── progression.ts, upcoming.ts, mobility.ts
│   │   │   └── bodyComposition.ts
│   │   ├── App.tsx           # Router + QueryClient + layout
│   │   ├── main.tsx          # Entry point + SW registration
│   │   └── index.css         # Design system (CSS custom properties)
│   ├── public/               # PWA icons, static assets
│   ├── package.json
│   └── vite.config.ts        # Vite + PWA + proxy config
├── docs/
│   ├── plans/
│   │   ├── README.md         # ← START HERE: status of every plan, what's left
│   │   └── 000N-*.md         # One plan per change; carries its own record of
│   │                         #   what landed and what was wrong with it
│   └── decisions/            # ADRs — settled decisions and why
├── data/                     # Data storage (gitignored)
│   ├── helf.db               # Live copy of production. WAL on: back up with
│   │                         #   `scripts/backup-db.sh`, never `cp`
│   └── *.bak                 # Every backup ever taken. Never pruned — the
│                             #   whole history is ~3MB apiece and kept
├── scripts/
│   ├── backup-db.sh          # The only correct way to copy a live WAL database
│   └── pre-migration-backup.sh   # PreToolUse hook: backs up before alembic
│                             #   upgrade/downgrade/stamp, blocks if it can't
├── Dockerfile                # Multi-stage build (Node 20 + Python 3.12)
├── docker-compose.yml
├── .env.example
└── LICENSE
```

## The data model, and the invariants that hold it together

**Read this before touching the schema.** The column lists are deliberately not
written down anywhere — they go stale and are then believed. What follows is the
*shape*, which does not.

### Two grains

**Training is flat.** A `workouts` row is one logged set; a session is the rows
sharing a `date`, ordered by `order`. Plan 0004 would make sessions a real
entity and is **deferred** — the MCP write path adapts a session-shaped tool
onto flat rows instead.

**Planned training is flat too, and holds two programs.**
`upcoming_workouts.kind` is `lifting` or `mobility`: same shape — an ordered
list of prescribed sets waiting to be copied onto a date — written by different
authors. Lifting comes from a Liftoscript program the user edits; mobility is
one rolling routine the agent rewrites each session (Plan 0012).

The cost is that **every query must name its kind**. A missing filter does not
error, it mixes the two: `delete_all()` unscoped would let generating a
Liftoscript program destroy the pending mobility session. Repository methods
default to `lifting`.

**Everything measured is tall.** An `observation` is one act of measuring — an
instant and an instrument — carrying `metric` rows whose names come from a fixed
vocabulary in `metric_def`. Adding a *quantity* is a row. Adding a *name* is a
migration, on purpose: the name carries the unit, so `vitamin_d_iu` cannot
quietly become mcg later.

### Units live in names

Pounds are canonical for body mass (ADR-0003) and **no row carries a unit
column**. `body_weight_lb`, `bone_mass_kg`. Two traps:

- `muscle_pct` is a **percentage** despite the API calling it `muscle_mass` — it
  correlates with body weight at r = −0.985, the signature of a fraction.
- `bone_mass_kg` is kilograms while its neighbours are pounds, because DEXA
  sub-masses are all kg (Plan 0008) and openScale reports kg. A pounds copy
  would put one quantity under two names.

### `doc_id` is an `observation.id`

Not a `body_composition.id` — that table is gone (Plan 0010), and the two
sequences disagreed on 77 of 150 rows, so treating one as the other deleted a
different measurement than the user asked for. The alias itself is TinyDB
legacy; FastAPI serialises by alias, so the JSON key is `doc_id`, never `id`.

### Three instruments write body composition, and they disagree

`observation.source` is `openscale`, `bodyspec` or `dexafit`. They measure the
same quantities with different instruments and **must never be averaged or
differenced across**. On 2026-03-10 the scale read 6.15 percentage points of
body fat above the DEXA scan taken hours later — that gap is the instruments,
not the body.

The read path is source-aware: `BodyCompositionStats.primary_source` names the
single series its deltas describe, and `/trends` returns a `sources` array
parallel to `dates` so a chart can keep them as separate marks. See
`docs/plans/0003-units-and-metrics.md` §4a.

### Intake, and supplements as foods

`food` carries macros per serving; `food_log` carries consumption events, and a
serving's numbers are **derived at read time** — so correcting a food corrects
every past entry. That is intended, and it is why `PUT /api/food/{id}` is a
deliberate act rather than something logging does implicitly.

A **supplement is a `food` row** with `kind = 'supplement'`, not a separate
table: whey is food by any definition at 120 kcal a scoop, and the boundary is
not somewhere a schema can put it. `stack` + `stack_item` are the grouping, with
`servings` on the membership so one product can be taken two ways.

**One table, two reads** (plan 0016). That storage argument is about storage,
and it was taken to settle presentation too, which it does not: a dose that
carries no meal, no macros and no calories has no business under breakfast.
Every read on the food side is now `kind='food'` — `/api/food/day`, the
`entries` count, and which days the summary considers logged — and supplements
are listed only on `/supplements`. The boundary the schema cannot draw is drawn
by hand instead: **anything carrying calories is logged as `kind='food'`**,
whey included.

The edge that leaves: a supplement *with* macros still counts toward the day's
totals while its entry sits on the other tab, because `v_daily_summary` sums
`food_log` without regard to kind and filtering it would hide a real calorie
entirely. The supplements log prints the kcal on any dose that has them.

**`food_log` carries no `stack_id`.** A log row records what was consumed; the
stack is only how it was entered. `taken_today` is derived — every one of the
stack's foods appears in today's log — so it holds whether the button was tapped
or the items entered by hand, and editing a stack cannot rewrite the past.

`foods_missing_macros` counts **meals only**. A vitamin has no macros to be
missing and would otherwise flag every fully logged day forever.

### `v_daily_summary` is the cross-domain join

Volume, intake, macros, body weight, mood, notes and `kcal_target` on one day
spine. **`kcal_target` is measured, not assumed** — the last DEXA scan's
Katch-McArdle RMR on or before that day, times 1.4. NULL before the first scan,
deliberately: a target no measurement supports is worse than a blank.

Adding a column per tracked thing would rebuild the wide table Plan 0010 just
retired. `supplements_taken` is a count for that reason.

### Mobility is a property of the set, and the day is derived

`workouts.is_mobility` is one boolean per logged set. Not per movement, and not
per day.

**Not per movement**, because a mobility routine borrows movements that are
also lifting movements — a good morning is a loaded hinge in one session and a
loaded stretch in the next, and one exercise row cannot hold both answers. This
was `exercises.is_mobility` until plan 0013 and the flag was in the wrong
place: "the last day containing a mobility exercise" finds lifting days too, as
2026-06-25 does — a pigeon squat and a calf raise logged beside a Romanian
deadlift.

**Not per day**, because a mobility session run alongside lifting is one day
and two sessions. 2026-08-13 is two sets of rehab work opening a twelve-set
shoulder day. A **mobility day is derived**: the most recent date carrying any
flagged set, and the read path returns *those sets*, not the whole day. There
is no marker that can disagree with the rows.

**There is deliberately no day-level marker, and one is not to be added back**
(plan 0013 §6). Not a note, not a column, not a "session focus". The sets
already say which day it was; anything stored beside them can only agree and be
redundant or disagree and be wrong. The version that existed for eleven days
needed a retroactive backfill *and* a second writer, and shared its row with
the agent's rationale so unticking it destroyed the reasoning.

One thing to know when editing a set: the flag is **sticky unless explicitly
sent**. Every other field on `WorkoutUpdate` is a full replace, so a PUT
carrying only a comment would clear it — and adding feedback to a set after
running it is precisely what happens to a mobility set. Told apart by
`model_fields_set`, the way `ExerciseUpdate.rating` distinguishes omitted from
null.

The `note` kinds still exist and no longer assert anything: `mobility_plan`
carries the pending session's rationale, `mobility_session` carries a run
session's, dated to its day. Delete one and the session is still a mobility
session with no recorded reason — a gap in the record rather than a change to
what happened. That is the fix for the old marker, which shared a row with the
rationale so unticking a checkbox destroyed the reasoning.

The user's feedback is **only** in `workouts.comment` on the logged sets. There
is no per-session feedback field, so program-level remarks ("keep this to 7
movements max") arrive attached to whichever set was on screen (Plan 0012 §4).
The read tool returns every comment on the *mobility sets* it hands back — so a
program-level remark left on a lifting set that day is not in the result, which
is the price of returning the session rather than the day.

### The journal is not the audit log

| | `note` / `document` | `audit_log` |
|---|---|---|
| Records | Observations about the world | Mutations to other tables |
| Written by | You and the agent | Database triggers |
| Lifecycle | Staging — *expected* to be restructured | **Immutable forever** |

Prose goes in `note`; raw payloads stay whole in `document.raw` behind a
`json_valid` check. A named scalar over time is neither — it has a shape
already and belongs in `metric`. The promotion pathway is
`docs/plans/0005-food-and-notes.md` §1a.

### Mutations are audited by triggers, and the log cannot be rewritten

`audit_log` records UPDATEs and DELETEs — plus INSERTs on `metric` and
`exercises`, where an insert can silently replace or invent something — for
`metric`, `food`, `food_log`, `note`, `workouts`, `exercises`, `stack` and
`stack_item`. It is populated **by database triggers, not by this application**:
there are two writers (ADR-0002) and application-level auditing would cover one
of them. `BEFORE UPDATE`/`BEFORE DELETE` triggers `RAISE(ABORT, 'audit_log is
append-only')`.

`actor` comes from the one-row `audit_actor` table, which defaults to `'app'`. A
second writer claims it with `BEGIN IMMEDIATE` **before** setting it and resets
it inside the same transaction; the write lock is what keeps the claim from
bleeding onto a concurrent writer's rows. A `TEMP` marker table cannot be used —
SQLite forbids triggers from reading `temp`, and an unqualified name binds to
`main` at compile time. See `docs/plans/0007-audit-log.md` §9.

## The agent reads this database over MCP, read-only by default

`backend/app/mcp/qs_mcp.py` is a stdio MCP server that opens `data/helf.db`
directly — a second process on the same file, not a second code path
(ADR-0002). It imports nothing from `app` except `config`, and even that is
deferred: a stdio server is launched with an arbitrary working directory, and
`Settings` reads a relative `.env` and creates `../data` on import.

```bash
cd backend && QS_DB_PATH=../data/helf.db .venv/bin/python -m app.mcp.qs_mcp
```

- **`QS_MCP_MODE` defaults to `read-only`**, and gating works by *not
  registering* the write tools. A tool that does not exist cannot be attempted
  or argued with; one that answers "not permitted" invites retries.
- **One tool is exempt.** `write_next_mobility_session` is registered in both
  modes (`ALWAYS_TOOLS`), because the mobility loop's whole value is the agent
  writing the next session. Read-only therefore means "the general-purpose
  write tools are absent", not "this process cannot write" — see Plan 0012 §5
  and the amendment on ADR-0004.
- **`query` always runs on a `mode=ro` connection**, in either mode. The
  privilege boundary is the connection, not the tool name (ADR-0004).
- Tool functions are plain functions; `build_server()` assembles the server.
  That is what makes the write path testable without an MCP client.
- Server instructions live in `docs/design/mcp-instructions.md` and are loaded
  at startup. Missing is fatal — an agent without them misreads this database
  confidently.

## Architecture Layers

### Backend
1. **API routes** (`api/`): HTTP handling, request parsing, response formatting. No business logic.
2. **Services** (`services/`): Business logic, calculations, external integrations (MQTT).
3. **Repositories** (`repositories/`): SQLAlchemy queries. Auto-creates exercises/categories on reference.
4. **Pydantic models** (`models/`): Request/response validation. **Deliberately
   separate from the ORM models** — they are the HTTP contract, not the storage
   shape, and the two have diverged. The body-composition response has no table
   behind it; it is built from a view over the tall `metric` store, which is why
   dropping the old wide table changed nothing for the frontend. Repositories
   return **dicts**, never ORM instances, so sessions can close inside them.
5. **DB models** (`db/models.py`): SQLAlchemy table definitions. Every table
   carries a docstring saying what it is for and why it is shaped that way —
   the closest thing to a schema reference, kept honest by `alembic check`.
6. **MCP server** (`app/mcp/`): **not** one of these layers. A separate process
   on the same file, raw SQL, importing only `config` (ADR-0002).

Validation is duplicated on purpose. `meal` is a Pydantic `Literal` *and* a
SQLite `CHECK`; `food.brand` has a validator *and* `NOT NULL DEFAULT ''`. The
agent writes raw SQL and never passes through Pydantic, so the constraint is the
only rule both writers obey.

### Frontend
1. **Pages** (`pages/`): Route-level components with layout and data fetching.
2. **Hooks** (`hooks/`): React Query hooks wrapping API calls with optimistic updates.
3. **API client** (`lib/api.ts`): Axios instance with typed API function groups.
4. **Types** (`types/`): TypeScript interfaces matching backend Pydantic schemas.
5. **Components** (`components/`): Reusable UI components (shadcn/ui + custom).

## Development Setup

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --port 8000
```

API documentation available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Frontend
```bash
cd frontend
npm install
npm run dev  # Runs on http://localhost:5173, proxies /api to :8000
```

### Full Stack Development
Run backend on port 8000 and frontend on port 5173. The frontend's Vite dev server proxies `/api` requests to the backend.

## Docker Deployment

### Quick Start
```bash
cp .env.example .env
# Edit .env to set HELF_DATA_PATH
docker-compose up -d
# App available at http://localhost:30171
```

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `HELF_DATA_PATH` | - | Host path for data volume mount |
| `DATA_DIR` | `/app/data` | Container path for SQLite database |
| `MQTT_ENABLED` | *(unset)* | Switches the retired MQTT ingest back on |
| `MQTT_BROKER_HOST` | `host.docker.internal` | MQTT broker hostname (only when enabled) |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `PRODUCTION` | `true` | Production mode flag |

## API Endpoints

### Workouts (`/api/workouts`)
- `GET /` - List workouts (optional `?date=YYYY-MM-DD`, `?skip=`, `?limit=`)
- `GET /calendar?year=X&month=Y` - Calendar workout counts per day
- `GET /{id}` - Get single workout
- `POST /` - Create workout
- `PUT /{id}` - Update workout
- `DELETE /{id}` - Delete workout
- `PATCH /reorder` - Bulk reorder (drag-and-drop)
- `PATCH /{id}/complete` - Toggle workout completion
- `POST /date/{source_date}/move` - Move all workouts to different date
- `POST /date/{source_date}/copy` - Copy all workouts to different date
- `PATCH /date/{date}/mobility` - Flag every set on a day as mobility work, or
  clear every one. A bulk edit of the per-set flag, **not** a day-level marker
  (plan 0013 §6): nothing is stored about the day, and a day whose sets
  disagree stays valid. Idempotent — `changed` counts rows actually written and
  is 0 when the day is already in that state, because every UPDATE fires an
  audit trigger and `audit_log` cannot be tidied afterwards. 404 on a day with
  nothing logged

### Exercises (`/api/exercises`)
- `GET /` - List all exercises
- `GET /recent?limit=N` - Recently used exercises
- `GET /{name}` - Get exercise by name
- `POST /` - Create exercise
- `PUT /{id}` - Update exercise. Omitting a key leaves it alone; sending
  `rating: null` *clears* the rating — the two are told apart by
  `model_fields_set`, not by value
- `DELETE /{id}` - Delete exercise
- `POST /seed` - Generate preset exercises (16 across 6 categories)
- `GET /categories/` - List categories
- `GET /categories/{name}` - Get category by name
- `GET /categories/{name}/exercises` - Exercises in category
- `POST /categories/` - Create category

### Progression (`/api/progression`)
- `GET /` - Main lifts progression (Bench, Squat, Deadlift)
- `GET /{exercise}` - Single exercise progression with 1RM estimates
- `GET /exercises/list` - Available exercises for dropdown

### Upcoming Workouts (`/api/upcoming`)
- `GET /` - List all upcoming workouts (grouped by session)
- `GET /session/{session}` - Get workouts for a specific session
- `POST /` - Create single upcoming workout
- `POST /bulk` - Create multiple upcoming workouts
- `DELETE /session/{session}` - Delete all workouts in a session
- `POST /session/{session}/transfer` - Transfer session to historical workouts
- `GET /wendler/maxes` - Current estimated 1RM for main lifts
- `POST /liftoscript/generate` - Parse Liftoscript and generate workout sessions
- `GET /presets` - List available workout presets
- `GET /presets/{name}` - Get preset script content

### Body Composition (`/api/body-composition`)
- `GET /` - List measurements (optional date range filter)
- `GET /latest` - Most recent measurement
- `GET /stats` - Summary statistics
- `GET /trends?days=N` - Trend data for charts (1-365 days)
- `POST /` - Create measurement by hand. Writes `source='manual'` and has no
  field to override it — the scale drain is a **different** endpoint for that
  reason
- `POST /sync/scale` - Drain the scale's onboard memory. Takes the whole
  replay as a batch, fixes `source='openscale'` at the route, and reports
  `imported`/`skipped`; a high `skipped` is the normal case, since the scale
  replays everything it holds
- `DELETE /{id}` - Delete measurement

### Food (`/api/food`)
- `GET /day?date=` - One day's totals *and* entries, read together. **Meals
  only** — supplements share the table but not this page (plan 0016), and
  `totals.entries` counts meals for the same reason
- `GET /log?date=&kind=` - The whole log for a day; `kind` narrows it to one of
  the two. Unfiltered it returns both, because it is the log for a date
- `GET /log/recent?kind=&limit=` - Entries across days, newest first. The
  supplements page's log. Deliberately not date-scoped: a dose filed against
  the wrong day is invisible to any per-day view
- `GET /log/summary?start&end` - Daily kcal + macro totals (days with nothing logged are absent, not zero; a day of supplements alone is not a logged day)
- `POST /log` - Log a consumption event (by `food_id`, or name a food to create it)
- `DELETE /log/{id}`
- `GET /?q=&kind=` - Search the catalog; `kind` is `food` or `supplement`
- `GET /{id}/usage` - How much history an edit would rewrite: entry count, date span, and the stacks using it
- `POST /` - Create a food
- `GET /{id}` / `PUT /{id}` - Read / edit macros (**retroactive** — rewrites every past entry). 409 if the new `(name, brand)` is taken

### Stacks (`/api/stacks`)
- `GET /` - All stacks, each with `taken_today` and `last_taken`
- `POST /` - Create a stack; items naming an unknown food create it
- `GET /{id}` / `PUT /{id}` / `DELETE /{id}` - `items` on PUT **replaces** the membership
- `POST /{id}/log` - Write one `food_log` row per item, at one instant

### Mobility (`/api/mobility`)
- `GET /pending` - **Every** pending session, each with its `label`, rationale
  and movements, plus the last session that was run. `ready` is derived from
  whether any session has items, and is the page's whole state discriminator.
  A plan row with no items is omitted rather than shown as an empty heading
- `POST /transfer` - Copy **one** pending session (named by `session`) onto a
  date, appending after anything already logged that day, and flag the sets as
  mobility work. Transferring one leaves the others pending
- `DELETE /pending/{session}` - Discard one pending session without running it,
  taking both its rows and the plan row that names them
There are deliberately **no endpoints here for creating a session or for
marking one**. The session is written by the agent over MCP, which is the point
of the feature; and which sets were mobility work is a field on the set,
written through the normal workout routes (`PUT /api/workouts/{id}` with
`is_mobility`). A day carrying any flagged set *is* a mobility day — there is
nothing separate to assert (plan 0013).

### Notes (`/api/notes`)
- `GET /?kind=&start=&end=` - Notes, most recent first
- `GET /kinds` - Counts and date spans per kind, across notes and documents
- `POST /` - Write a note
- `GET /{id}` / `DELETE /{id}`

### System
- `GET /api/health` - Health check
- `GET /api/mqtt/status` - Reports `enabled` **and** `connected`. They are
  separate because a retired ingest and a dead broker used to give the same
  answer
- `POST /api/mqtt/reconnect` - 409 when ingest is disabled, rather than a 200
  that reconnects nothing

## Frontend Routes

| Path | Page | Description |
|---|---|---|
| `/` | Calendar | Month view with workout count indicators + streak |
| `/day/:date` | WorkoutSession | Log exercises, drag-reorder, mark complete, flag sets as mobility work individually or a whole day at once |
| `/progression` | Progression | Main lifts (Bench/Squat/Deadlift) 1RM charts |
| `/progression/:exercise` | Progression | Single exercise 1RM chart |
| `/body-composition` | BodyComposition | Trends, stats, DEXA import — tab 1 of the Body section |
| `/food` | Food | Daily log, intake against `kcal_target` — tab 2 of the Body section (ADR-0006) |
| `/supplements` | Supplements | Preset groups logged in one tap, plus every dose logged — tab 3 of the Body section |
| `/upcoming` | Upcoming | Session planner, Liftoscript editor, presets — tab 1 of the Upcoming section |
| `/mobility` | Mobility | The next mobility session, ready to copy or awaiting generation — tab 2 of the Upcoming section |
| `/exercises` | Exercises | Browse/manage exercise catalog by category |

## Key Features

### Workout Tracking
- Calendar view with workout count indicators and training streak
- Exercise logging with category-based organization
- Set tracking: weight, reps (an **integer** — no AMRAP notation in the data
  model, ADR-0005; `5+` is Liftoscript source only and resolves to a comment)
- Optional fields: distance, time, comments
- Drag-to-reorder exercises within sessions (dnd-kit)
- Move/copy all workouts between dates
- Toggle completion status per exercise

### Progression Tracking
- 1RM estimation formula: `(0.033 x reps x weight) + weight`
- Interactive charts with Recharts
- Configurable moving averages
- Future projections from upcoming workouts
- Main lifts quick access (Bench, Squat, Deadlift)

### Workout Planning (Liftoscript)
- Session-based upcoming workout management
- Custom Liftoscript scripting language for defining programs
- Built-in presets: Wendler 5/3/1, StrongLifts 5x5
- Percentage-based weights (% of 1RM)
- Linear progression: `progress: lp(5lb)`
- Multi-cycle generation
- One-click transfer to historical data

### Food and intake
- Catalog with macros per serving; log with servings, meal and time
- Running daily totals against `kcal_target`, which comes from the last DEXA
  scan's measured resting rate rather than a formula
- Days with nothing logged are absent from the summary, not zero — an unlogged
  day and a fasted day are different facts
- Supplements are **not** listed here — separate page, separate read (plan 0016)
- Lives at `/food`, tab 2 of the Body section (ADR-0006)

### Supplements and stacks
- Named groups logged in one tap: "morning" is omega ×2, vitamin D ×1,
  CholestOff ×2
- A product can sit in several groups at different servings
- Adherence shows as "taken today", derived from the log rather than from the
  button
- **Recent doses** at the bottom of the page: every dose across days, newest
  first, with a two-tap delete — the counterpart of the body page's measurement
  log, and not date-scoped for the same reason
- **Nothing appears on the Food tab.** The two pages are separate reads over
  one table (plan 0016); log anything with calories as a food
- Lives at `/supplements`, tab 3 of the Body section

*Why supplements are `food` rows and why the log has no `stack_id`: see the data
model section above.*

### Mobility
- **Rolling routines**, each adjusted a session at a time from the last
  session's feedback — not programs generated in advance and then followed
- **Several can be pending at once**, one per `label` ("Low back",
  "Shoulder"), because rehabbing two areas means two prescriptions alive on
  different schedules. The label is the agent's addressing key: a new one adds
  a session, an existing one replaces *that* session and cannot touch the
  others. The user picks which to run from `/mobility`
- The agent drives it over MCP: `read_latest_mobility_session(date=…)` returns
  a mobility session's sets and every comment on them — the most recent day
  with flagged sets, or a day you name — and
  `write_next_mobility_session(label, …)` writes one pending session and
  records why
- **Which sets it reads is the per-set toggle** on `/day/:date`, beside the
  completion tick, with a **Mark all mobility** button in the day's header for
  the common case where the whole day was one. The button writes the same
  per-set flag N times in one request; it stores nothing about the day. Transfer sets it for a prescribed session; tapping it by
  hand is how a session that never went through the planner becomes the one the
  next prescription is written from. The last day with any flagged set is that
  session, and only its flagged sets are returned
- The philosophy is **loaded stretching** — strengthen through full range rather
  than holding static stretches
- **The standing program rules are the user's, and `docs/design/mcp-instructions.md`
  is the only place they are written down.** How many movements a routine may
  hold, what is programmed first, where static stretches sit relative to their
  loaded movement — that file is loaded verbatim into the agent's context at
  startup, so a copy here is a copy that changes without it. Do not restate
  them in this file; read them there
- There is no movement pool table and no flag on the exercise. Each movement
  carries **two** fields: `form` (how to perform it — reference material) and
  `application` (symptom → likely cause → what to change). The second is what
  turns a comment into a programming decision, and it is separate from `form`
  so that the agent recording what a session taught it cannot damage how the
  movement is performed — with one blob it had to re-emit the setup
  instructions from memory on every write
- `rating` on those movements is **enjoyment**, not value. It protects
  adherence; how much a movement is worth lives in `application`, and the
  divergence between the two is the useful signal
- Movement `form` text was imported from an Obsidian vault by
  `backend/migrations/import_mobility_pool.py` (one-shot, and it predates
  plan 0013 — see the header note in that file)

### Body Composition
- **Read straight from the scale in the browser** over Web Bluetooth (plan
  0015): the BF720 speaks the Bluetooth SIG Body Composition Service, so no
  phone, no openScale, no broker. One tap drains its 30-reading memory;
  duplicates are refused by `UNIQUE (observed_at, source)` rather than tracked
  client-side
- MQTT ingest (openScale-sync format) is **retired but not deleted** — it is
  the fallback for a scale the browser cannot read, since the decoder handles
  the SIG profile only while openScale drives around a hundred scales. Set
  `MQTT_ENABLED=true`
- BodySpec DEXA import — paste a token, used for one request and stored nowhere
- Weight, body fat %, muscle %, water %, plus DEXA masses and a computed RMR
- Trends with configurable periods; the scale is a line, DEXA is unjoined points
- Stats name the instrument their deltas describe
- Manual entry support

### Exercise Management
- Browse exercises by category
- Seed database with 16 preset exercises across 6 categories
- Track usage count and last-used date
- CRUD for exercises and categories
- **`rating`** (1–5, NULL is *unrated*) is a judgement about the movement, kept
  on the exercise rather than copied onto its sets, so re-rating rewrites no
  history. Edited inline on `/exercises`, and audited — which is why the
  migrations that added and later reshaped it rebuilt the `exercises` triggers.
- **`form` and `application`** are the two halves of what used to be one
  `notes` blob (`e2b9c4d17a05`). Form is how to perform the movement;
  application is symptom → likely cause → what to change. Different authors,
  different lifetimes: the user writes form once, the agent supersedes
  application as it learns. Both are edited on `/exercises` and both are
  audited.
- There is **no mobility flag on an exercise** (plan 0013). Whether a movement
  is mobility work depends on the objective that day, so it lives on the set;
  `rating` stays here precisely because it is an opinion about the movement and
  not about one performance of it.

### PWA Features
- Offline support with service worker (Workbox)
- Installable on mobile/desktop
- Auto-update with user prompt
- Cache-first for assets, network-first for API
- Online/offline status indicator

## Design System

The app follows a dark-first design philosophy with an orange accent.

> **Tailwind is v4, and `index.css` must start with `@import "tailwindcss"`.**
> It previously used the v3 `@tailwind base/components/utilities` directives,
> which v4 accepts and half-honours: plain utilities are still emitted, but the
> theme never loads, so **no variant generates any CSS** — no `md:`, no `lg:`,
> no `hover:`, no `disabled:`, no `focus:`. The built stylesheet had zero of
> them. Consequence: `nav-desktop` is `hidden md:block`, so the desktop nav had
> never rendered at any width, and the mobile bottom bar showed on desktop.
> `@config "../tailwind.config.js"` keeps the v3 config (the shadcn colour
> tokens) loaded. Do not "modernise" this back.

> **The design-system tokens and the shadcn tokens share a namespace, and they
> are different kinds of value.** The design system stores real colours
> (`--border: #2a2a2d`); shadcn stores bare HSL triplets meant to be wrapped
> (`hsl(var(--border-tw))`). Declaring the same name in both blocks means the
> later one wins and every `var(--border)` in the app receives `0 0% 16%` —
> which is not a colour, so `1px solid var(--border)` is dropped as invalid.
> That is what happened: **no border rendered anywhere in the app**, in 42
> places, until 2026-08-11. Shadcn-side names are therefore suffixed `-tw`
> (`--accent-tw`, `--border-tw`) and only Tailwind's config may consume them.
> A missing border is silent — nothing errors and the layout does not move — so
> the check is visual: if a dashed empty-state card has no dash, look here.

### Colors (CSS Variables in `frontend/src/index.css`)
- Backgrounds: `--bg-base` (#09090b), `--bg-primary`, `--bg-secondary`, `--bg-tertiary`, `--bg-hover`, `--bg-active`
- Text: `--text-primary` (#fafafa), `--text-secondary` (#a1a1a6), `--text-muted` (#5c5c5e)
- Accent: `--accent` (#f97316 orange), `--accent-hover`, `--accent-muted`, `--accent-glow`
- Semantic: `--success` (#22c55e), `--warning` (#eab308), `--error` (#ef4444), `--info` (#3b82f6)
- Chart palette: `--chart-1` (#f97316) through `--chart-5` (#eab308)

### Zoom is off, and it takes two changes not one

The viewport meta carries `user-scalable=no, maximum-scale=1`, and `body` has
`touch-action: manipulation`. That covers pinch and double-tap.

It does **not** cover the one that actually bit: iOS Safari zooms into a
focused text field whose `font-size` is under 16px, honours no viewport setting
while doing so, and never zooms back out — leaving every form off-centre on a
phone. So `@media (pointer: coarse)` forces `input, select, textarea` to 16px
with `!important`, which is load-bearing because some fields set their size
inline. **Removing either half brings the bug back**, and it cannot be
reproduced in desktop Chrome.

### Typography
- Display font: Clash Display (headings) - from Fontshare
- Body font: Satoshi (UI text) - from Fontshare
- Mono font: JetBrains Mono (numbers, stats) - from Google Fonts

### Spacing & Layout
- 4px base spacing system (`--space-1` through `--space-16`)
- Border radius: `--radius-sm` (6px) to `--radius-full` (9999px)
- Shadows: `--shadow-sm` to `--shadow-lg` + `--shadow-glow`
- Durations: `--duration-fast` (100ms), `--duration-normal` (150ms), `--duration-slow` (250ms)

### Components
- Use `<Button>` component (shadcn/ui with CVA variants)
- Use `<Input>` component for form fields
- Use `<Card>` component for containers
- Use `<Select>` component for dropdowns (Radix UI)
- Navigation: desktop sidebar (`nav-desktop`) + mobile bottom bar (`nav-mobile`)

## Backups, and why none are deleted

**Every migration takes a backup, and every backup is kept.** Not the newest
few — all of them. The database is ~3MB, so the entire history of the schema
costs less than a phone photo, and the one you discover you need is always the
one a retention policy would have thrown away.

Take one with the script, never with `cp`:

```bash
scripts/backup-db.sh pre-0013     # -> data/helf.db.pre-0013.bak
scripts/backup-db.sh              # -> data/helf.db.auto-<stamp>.bak
```

It uses SQLite's online backup API, so it is correct **while the app is
running** — `cp` is not, because committed pages may still be in `helf.db-wal`.
It then reopens the result `immutable=1`, runs `integrity_check`, and prints
row counts and the Alembic revision. A backup that is silently corrupt is worse
than none, because it is trusted.

**You should rarely need to run it by hand.** `scripts/pre-migration-backup.sh`
is a PreToolUse hook on `Bash`, **registered in `.claude/settings.json`** —
which is the one file inside `.claude/` that is *not* gitignored, so the hook
travels with the repo. It fires on anything naming alembic and a verb that
changes the schema, and takes a backup first.

> It was described here as an active hook for nine days while being registered
> nowhere, and `e2b9c4d17a05` reached production with no backup behind it. A
> mechanism that lives only in an ignored file is a mechanism the next clone
> does not have. `backend/tests/test_pre_migration_hook.py` now drives the real
> script with real payloads, so the matcher cannot silently stop matching. It *creates* the backup rather than blocking the command — a block
teaches a model to route around it, a backup that always exists has nothing
worth routing around — but it does fail loud and block if the backup itself
fails. Migrations that run back-to-back reuse a snapshot under 10 minutes old.

Three rules follow from keeping everything:

- **Never delete a `.bak`.** Not to tidy up, not because it looks redundant.
- **Never overwrite one.** `backup-db.sh` refuses a label that already exists;
  pick a new one rather than forcing it.
- **Label deliberate backups** (`pre-0013`, `pre-dexafit-backfill`) so the file
  name says what it is a backup *of*. The `auto-<stamp>` ones are the hook's.

`data/` is gitignored, so this history exists **only on disk**. It is not in
git and not in the image; it lives or dies with the volume at
`${HELF_DATA_PATH}`.

A backup should have no `-wal` or `-shm` beside it. `.backup` leaves a fully
checkpointed file, so a sidecar means something opened that backup read-write
and it is no longer the frozen thing you think it is.

## Testing

Fixtures build the database by **running the real migrations** (`conftest` does
`upgrade head`) against a temporary file — not `Base.metadata.create_all()`, and
not in memory. The read path queries views and `metric_def` carries a seeded
vocabulary, neither of which exists in metadata, so `create_all()` produces a
database the application cannot run against. **New tables and seeds must
therefore arrive via a migration.**

One trap worth naming: `from app.database import SessionLocal` at module scope
binds the *production* engine, and is only safe if `conftest`'s patch list
happens to name that module. Reference `database.SessionLocal` through the
module instead. A test that gets this wrong writes to `data/helf.db`.

```bash
# Backend tests
cd backend
pytest
pytest -v                                    # verbose
pytest tests/test_services_liftoscript.py    # specific file
pytest --cov=app                             # coverage

# Migrations
.venv/bin/alembic current                    # current revision
.venv/bin/alembic check                      # drift between ORM and migrations
.venv/bin/alembic upgrade head

# Frontend lint, page tests, type check + build
cd frontend
npm run lint
npm test        # jsdom mounts of the pages
npm run build   # includes tsc

# Type check + build
npm run build  # Includes tsc
```

## Common Tasks

### Add a new API endpoint
1. Create Pydantic schemas in `backend/app/models/`
2. Add repository methods in `backend/app/repositories/`
3. (Optional) Add service logic in `backend/app/services/`
4. Create route handler in `backend/app/api/`
5. Register router in `backend/app/main.py`
6. Add tests in `backend/tests/`

### Add a new frontend page
1. Create page component in `frontend/src/pages/`
2. Add React Query hooks in `frontend/src/hooks/`
3. Add API functions in `frontend/src/lib/api.ts`
4. Add types in `frontend/src/types/`
5. Register route in `frontend/src/App.tsx`
6. Add navigation link in `frontend/src/components/Navigation.tsx`
7. Add SPA route handler in `backend/app/main.py` (for production serving)

### Update the design system
1. Modify CSS variables in `frontend/src/index.css`
2. Update component styles consistently
3. Follow existing patterns in shadcn/ui components

## Troubleshooting

### Frontend not loading in Docker
- Verify static files built: `docker exec helf-app ls /app/static`
- Check API health: `curl http://localhost:30171/api/health`

### MQTT not connecting

**First check whether it is meant to be.** Ingest is off by default since plan
0015 — `GET /api/mqtt/status` returns `enabled: false`, and that is not a
fault. Set `MQTT_ENABLED=true` only if you are using it for another scale.
- Verify broker is running on host
- Check `MQTT_BROKER_HOST` configuration
- View status: `curl http://localhost:30171/api/mqtt/status`
- Trigger reconnect: `curl -X POST http://localhost:30171/api/mqtt/reconnect`

### Database issues
- Check data directory permissions
- Verify `helf.db` exists in data directory
- Review container logs: `docker logs helf-app`

## Git Workflow

### Branches
- `main` - Production-ready code. **Commit directly to it; do not branch first.**

### Commits
- Use conventional commit messages
- **Lead with why the old state was wrong**, not just what changed. The commit
  log is the record of what was learned; `git log` on this repo is worth reading
- Record verification in the message — counts *and* checksums against the real
  database, not just "tests pass"
- Include Claude Code attribution when AI-assisted

### Ignored Files
- `**/helf.db` - SQLite database
- `**/helf.json` - Legacy TinyDB export
- `.claude/` - Claude documentation
- `.venv/`, `backend/.venv/` - Python virtual environments
- `node_modules/` - Node dependencies
- `data/` - Runtime data directory

## Architecture Decisions

Formal ADRs live in [`docs/decisions/`](docs/decisions/) and are **settled** —
read the ADR before proposing a change to what it covers.

| ADR | Decision |
|---|---|
| [0001](docs/decisions/0001-record-architecture-decisions.md) | Record decisions, because the reasoning is what's worth keeping |
| [0002](docs/decisions/0002-sqlalchemy-for-app-raw-sql-for-agent.md) | SQLAlchemy for the app, raw SQL for the agent |
| [0003](docs/decisions/0003-pounds-as-canonical-unit.md) | **Pounds are canonical for body mass**; units live in metric *names*; no row carries a unit column |
| [0004](docs/decisions/0004-mcp-server-over-rest-for-agent-access.md) | MCP over REST for agent access — and read-only is **not** a confidentiality control, so nothing secret goes in `helf.db` |
| [0005](docs/decisions/0005-no-amrap-in-the-data-model.md) | No AMRAP notation; `reps` is an integer |
| [0006](docs/decisions/0006-food-is-a-tab-under-body-not-a-sixth-nav-item.md) | The mobile nav bar is **full at five**; a new destination is a tab beside an existing one |

ADR-0004 carries an amendment: one mobility write tool is registered in both
MCP modes (Plan 0012 §5), so `read-only` describes the default tool set rather
than the process. The connection is still the privilege boundary.

Earlier choices, predating the ADR practice:

1. **SQLite over TinyDB**: Better performance and query flexibility for growing datasets
2. **Repository Pattern**: Clean separation between data access and business logic
3. **React Query over Redux**: Better suited for server state management with optimistic updates
4. **Recharts over Plotly**: Better React integration, smaller bundle size
5. **shadcn/ui**: Customizable components without heavy dependencies
6. **dnd-kit**: Modern drag-and-drop library with accessibility support
7. **Liftoscript**: Custom DSL for defining workout programs, simpler than full programming languages

## Migration from v1.x

If migrating from a legacy TinyDB JSON export:
```bash
cd backend
python migrations/tinydb_to_sqlite.py
```
This converts TinyDB JSON to SQLite while preserving your existing data.

---

**Version**: 2.0.0
**Architecture**: FastAPI + React 19 + SQLite
**Last Updated**: 2026-08-10

Current schema and integration state is **not** recorded here — it would go
stale. See [`docs/plans/README.md`](docs/plans/README.md), which gives the
commands that report it.
