# Helf - Health & Fitness Tracker

## Project Overview

Helf is a modern Progressive Web App (PWA) for tracking workouts, monitoring body composition, and planning training sessions. Refactored from a NiceGUI monolith to a FastAPI + React architecture.

**Status**: Production Ready (v2.0.0)

## Tech Stack

### Backend
- **Framework**: FastAPI 0.127+
- **Database**: SQLite + SQLAlchemy 2.x
- **MQTT**: Paho-MQTT 2.1+ (smart scale integration)
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
│   │   │   └── body_comp.py
│   │   ├── db/
│   │   │   └── models.py     # SQLAlchemy ORM models (tables)
│   │   ├── models/           # Pydantic request/response schemas
│   │   │   ├── workout.py
│   │   │   ├── exercise.py
│   │   │   ├── progression.py
│   │   │   ├── upcoming.py
│   │   │   └── body_composition.py
│   │   ├── repositories/     # SQLAlchemy data access layer
│   │   │   ├── workout_repo.py
│   │   │   ├── exercise_repo.py
│   │   │   ├── upcoming_repo.py
│   │   │   └── body_comp_repo.py
│   │   ├── services/         # Business logic
│   │   │   ├── progression_service.py
│   │   │   ├── mqtt_service.py
│   │   │   ├── wendler_service.py
│   │   │   └── liftoscript_service.py
│   │   ├── utils/            # Helper functions
│   │   │   ├── calculations.py   # 1RM estimation, moving averages
│   │   │   └── date_helpers.py   # Timezone, date parsing/formatting
│   │   ├── presets/          # Built-in workout programs
│   │   │   ├── wendler_531.liftoscript
│   │   │   └── stronglifts_5x5.liftoscript
│   │   ├── config.py         # Pydantic BaseSettings (env vars)
│   │   ├── database.py       # SQLAlchemy engine/session/init
│   │   └── main.py           # FastAPI app, lifespan, CORS, SPA routing
│   ├── migrations/
│   │   ├── tinydb_to_sqlite.py   # Legacy data migration
│   │   └── add_exercise_notes.py # Schema migration
│   ├── tests/                # 18 pytest test files
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Navigation.tsx         # Desktop sidebar + mobile bottom bar
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
│   │   │   └── usePWA.ts             # Online status, install prompt
│   │   ├── lib/
│   │   │   └── api.ts        # Axios instance + all API functions
│   │   ├── pages/
│   │   │   ├── Calendar.tsx           # Month view + streak
│   │   │   ├── WorkoutSession.tsx     # Day view, log exercises
│   │   │   ├── Progression.tsx        # 1RM charts
│   │   │   ├── Upcoming.tsx           # Session planner + Liftoscript
│   │   │   ├── BodyComposition.tsx    # Trends + stats
│   │   │   └── Exercises.tsx          # Exercise catalog
│   │   ├── types/            # TypeScript type definitions
│   │   │   ├── workout.ts, exercise.ts
│   │   │   ├── progression.ts, upcoming.ts
│   │   │   └── bodyComposition.ts
│   │   ├── App.tsx           # Router + QueryClient + layout
│   │   ├── main.tsx          # Entry point + SW registration
│   │   └── index.css         # Design system (CSS custom properties)
│   ├── public/               # PWA icons, static assets
│   ├── package.json
│   └── vite.config.ts        # Vite + PWA + proxy config
├── data/                     # Data storage (gitignored)
│   └── helf.db
├── Dockerfile                # Multi-stage build (Node 20 + Python 3.12)
├── docker-compose.yml
├── .env.example
└── LICENSE
```

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
| `MQTT_BROKER_HOST` | `host.docker.internal` | MQTT broker hostname |
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

### Exercises (`/api/exercises`)
- `GET /` - List all exercises
- `GET /recent?limit=N` - Recently used exercises
- `GET /{name}` - Get exercise by name
- `POST /` - Create exercise
- `PUT /{id}` - Update exercise
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
- `POST /` - Create measurement (manual or from MQTT)
- `DELETE /{id}` - Delete measurement

### System
- `GET /api/health` - Health check
- `GET /api/mqtt/status` - MQTT connection status
- `POST /api/mqtt/reconnect` - Trigger MQTT reconnection

## Frontend Routes

| Path | Page | Description |
|---|---|---|
| `/` | Calendar | Month view with workout count indicators + streak |
| `/day/:date` | WorkoutSession | Log exercises, drag-reorder, mark complete |
| `/progression` | Progression | Main lifts (Bench/Squat/Deadlift) 1RM charts |
| `/progression/:exercise` | Progression | Single exercise 1RM chart |
| `/body-composition` | BodyComposition | Trends, stats, manual entry |
| `/upcoming` | Upcoming | Session planner, Liftoscript editor, presets |
| `/exercises` | Exercises | Browse/manage exercise catalog by category |

## Key Features

### Workout Tracking
- Calendar view with workout count indicators and training streak
- Exercise logging with category-based organization
- Set tracking: weight, reps (including AMRAP notation like "5+")
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

### Body Composition
- MQTT integration with smart scales (openScale-sync format)
- Metrics: weight, body fat %, muscle mass, BMI, water %, bone mass, visceral fat
- Trend visualization with configurable periods (1-365 days)
- Summary statistics with changes over time
- Manual entry support

### Exercise Management
- Browse exercises by category
- Seed database with 16 preset exercises across 6 categories
- Track usage count and last-used date
- CRUD for exercises and categories

### PWA Features
- Offline support with service worker (Workbox)
- Installable on mobile/desktop
- Auto-update with user prompt
- Cache-first for assets, network-first for API
- Online/offline status indicator

## Design System

The app follows a dark-first design philosophy with an orange accent.

### Colors (CSS Variables in `frontend/src/index.css`)
- Backgrounds: `--bg-base` (#09090b), `--bg-primary`, `--bg-secondary`, `--bg-tertiary`, `--bg-hover`, `--bg-active`
- Text: `--text-primary` (#fafafa), `--text-secondary` (#a1a1a6), `--text-muted` (#5c5c5e)
- Accent: `--accent` (#f97316 orange), `--accent-hover`, `--accent-muted`, `--accent-glow`
- Semantic: `--success` (#22c55e), `--warning` (#eab308), `--error` (#ef4444), `--info` (#3b82f6)
- Chart palette: `--chart-1` (#f97316) through `--chart-5` (#eab308)

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

## Architecture Layers

### Backend
1. **API routes** (`api/`): HTTP handling, request parsing, response formatting. No business logic.
2. **Services** (`services/`): Business logic, calculations, external integrations (MQTT).
3. **Repositories** (`repositories/`): SQLAlchemy queries. Auto-creates exercises/categories on reference.
4. **Pydantic models** (`models/`): Request/response validation. Separate from ORM models.
5. **DB models** (`db/models.py`): SQLAlchemy table definitions with relationships.

### Frontend
1. **Pages** (`pages/`): Route-level components with layout and data fetching.
2. **Hooks** (`hooks/`): React Query hooks wrapping API calls with optimistic updates.
3. **API client** (`lib/api.ts`): Axios instance with typed API function groups.
4. **Types** (`types/`): TypeScript interfaces matching backend Pydantic schemas.
5. **Components** (`components/`): Reusable UI components (shadcn/ui + custom).

## Testing

```bash
# Backend tests (pytest with in-memory SQLite)
cd backend
pytest
pytest -v                                    # verbose
pytest tests/test_services_liftoscript.py    # specific file
pytest --cov=app                             # coverage

# Frontend lint
cd frontend
npm run lint

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
- `main` - Production-ready code

### Commits
- Use conventional commit messages
- Include Claude Code attribution when AI-assisted

### Ignored Files
- `**/helf.db` - SQLite database
- `**/helf.json` - Legacy TinyDB export
- `.claude/` - Claude documentation
- `.venv/`, `backend/.venv/` - Python virtual environments
- `node_modules/` - Node dependencies
- `data/` - Runtime data directory

## Architecture Decisions

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
**Last Updated**: February 2026
