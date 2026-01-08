# Helf - Health & Fitness Tracker

## Project Overview

Helf is a modern Progressive Web App (PWA) for tracking workouts, monitoring body composition, and planning training sessions. The application has been fully refactored from a NiceGUI monolith to a FastAPI + React architecture.

**Status**: Production Ready (v2.0.0)

## Tech Stack

### Backend
- **Framework**: FastAPI 0.127+
- **Database**: SQLite + SQLAlchemy 2.x
- **MQTT**: Paho-MQTT 2.1+ (smart scale integration)
- **Validation**: Pydantic v2
- **Server**: Uvicorn with multi-worker support
- **Package Manager**: UV (with pyproject.toml)

### Frontend
- **Framework**: React 19+ with TypeScript
- **Build Tool**: Vite 7+
- **UI Components**: shadcn/ui (Radix UI + Tailwind)
- **Styling**: Tailwind CSS 4+
- **State Management**: TanStack Query (React Query) v5
- **Routing**: React Router v7
- **Charts**: Recharts
- **Icons**: Lucide React
- **Date Handling**: date-fns

### PWA
- **Plugin**: vite-plugin-pwa
- **Caching**: Workbox (cache-first assets, network-first API)
- **Features**: Offline support, installable, service worker

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
│   │   ├── models/           # Pydantic models
│   │   ├── repositories/     # SQLAlchemy data access layer
│   │   ├── services/         # Business logic
│   │   ├── utils/            # Helper functions (1RM calc, dates)
│   │   ├── config.py         # Application settings
│   │   ├── database.py       # SQLAlchemy session/engine
│   │   └── main.py           # FastAPI application entry
│   ├── migrations/
│   │   └── tinydb_to_sqlite.py  # TinyDB JSON migration script
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   │   ├── ui/           # shadcn/ui components
│   │   │   └── PWA/          # PWA-related components
│   │   ├── hooks/            # Custom React Query hooks
│   │   ├── lib/              # API client, utilities
│   │   ├── pages/            # Route page components
│   │   └── types/            # TypeScript type definitions
│   ├── public/               # Static assets, PWA icons
│   ├── package.json
│   └── vite.config.ts
├── data/                     # Data storage (gitignored)
│   └── helf.db               # SQLite database
├── tests/
├── Dockerfile                # Multi-stage build
├── docker-compose.yml
└── .claude/                  # Claude documentation (gitignored)
```

## Development Setup

### Backend
```bash
cd backend
source ../.venv/bin/activate  # Or create venv
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
npm run dev  # Runs on http://localhost:5173
```

### Full Stack Development
Run backend on port 8000 and frontend on port 5173. The frontend's Vite dev server proxies API requests to the backend.

## Docker Deployment

### Quick Start
```bash
docker-compose up -d
# App available at http://localhost:30171
```

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/app/data` | SQLite database directory |
| `MQTT_BROKER_HOST` | `host.docker.internal` | MQTT broker hostname |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `PRODUCTION` | `true` | Production mode flag |

### Data Persistence
Data is stored in `/mnt/fast/apps/helf/data` by default. Contains:
- `helf.db` - SQLite database

## API Endpoints

### Workouts (`/api/workouts`)
- `GET /` - List workouts (with pagination)
- `GET /?date=YYYY-MM-DD` - Get workouts by date
- `GET /calendar?year=X&month=Y` - Calendar workout counts
- `POST /` - Create workout
- `PUT /{id}` - Update workout
- `DELETE /{id}` - Delete workout
- `PATCH /{id}/reorder` - Reorder workout

### Exercises (`/api/exercises`)
- `GET /` - List all exercises
- `GET /recent?limit=N` - Recently used exercises
- `POST /` - Create exercise
- `GET /categories/` - List categories
- `POST /categories/` - Create category

### Progression (`/api/progression`)
- `GET /{exercise}` - Get progression data with 1RM estimates
- `GET /` - Main lifts progression (Bench, Squat, Deadlift)
- `GET /exercises/list` - Available exercises list

### Upcoming Workouts (`/api/upcoming`)
- `GET /` - List all upcoming workouts
- `POST /` - Create upcoming workout
- `POST /bulk` - Bulk import (Wendler 5/3/1 generator)
- `DELETE /session/{num}` - Delete session
- `POST /session/{num}/transfer` - Transfer to historical

### Body Composition (`/api/body-composition`)
- `GET /` - List measurements
- `GET /latest` - Latest measurement
- `GET /stats` - Summary statistics
- `GET /trends?days=N` - Trend data
- `POST /` - Create measurement (or via MQTT)
- `DELETE /{id}` - Delete measurement

### System
- `GET /api/health` - Health check
- `GET /api/mqtt/status` - MQTT connection status

## Key Features

### Workout Tracking
- Calendar view with workout count indicators
- Exercise logging with category-based organization
- Set tracking: weight, reps (including AMRAP notation like "5+")
- Optional fields: distance, time, comments
- Drag-to-reorder exercises within sessions

### Progression Tracking
- 1RM estimation formula: `(0.033 × reps × weight) + weight`
- Interactive charts with Recharts
- Configurable moving averages
- Future projections from upcoming workouts
- Main lifts quick access (Bench, Squat, Deadlift)

### Workout Planning
- Session-based upcoming workout management
- Bulk import
- Wendler 5/3/1 generator support
- One-click transfer to historical data

### Body Composition
- MQTT integration with smart scales (openScale-sync format)
- Metrics: weight, body fat %, muscle mass, BMI, water %, bone mass, visceral fat
- Trend visualization with configurable periods
- Automatic kg ↔ lbs conversion

### PWA Features
- Offline support with service worker
- Installable on mobile/desktop
- Auto-update with user prompt
- Cache-first for assets, network-first for API

## Design System

The app follows a dark-first design philosophy. Key principles:

### Colors (CSS Variables)
- Backgrounds: `--bg-base`, `--bg-primary`, `--bg-secondary`, `--bg-tertiary`
- Text: `--text-primary`, `--text-secondary`, `--text-muted`
- Accent: `--accent` (green #22c55e)
- Chart palette: `--chart-1` through `--chart-5`

### Typography
- Display font: Clash Display (headings)
- Body font: Satoshi (UI text)
- Mono font: JetBrains Mono (numbers, stats)

### Components
- Use `.card` CSS class for containers
- Use `<Button>` component (maps to `.btn-*` classes)
- Use `<Input>` component for form fields
- Use `.stat-card` for metric displays

See `.claude/DESIGN_SYSTEM.md` for complete specifications.

## Testing

```bash
# Backend tests
cd backend
pytest

# Frontend lint
cd frontend
npm run lint

# Type check
npm run build  # Includes tsc
```

## Common Tasks

### Add a new API endpoint
1. Create Pydantic models in `backend/app/models/`
2. Add repository methods in `backend/app/repositories/`
3. Create route handler in `backend/app/api/`
4. Register router in `backend/app/main.py`

### Add a new frontend page
1. Create page component in `frontend/src/pages/`
2. Add React Query hooks in `frontend/src/hooks/`
3. Register route in `frontend/src/App.tsx`
4. Add navigation link in `frontend/src/App.tsx`

### Update the design system
1. Modify CSS variables in `frontend/src/index.css`
2. Update component styles consistently
3. Follow patterns in `.claude/DESIGN_SYSTEM.md`

## Troubleshooting

### Frontend not loading in Docker
- Verify static files built: `docker exec helf-app ls /app/static`
- Check API health: `curl http://localhost:30171/api/health`

### MQTT not connecting
- Verify broker is running on host
- Check `MQTT_BROKER_HOST` configuration
- View status: `curl http://localhost:30171/api/mqtt/status`

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
- `.venv/` - Python virtual environment
- `node_modules/` - Node dependencies

## Architecture Decisions

1. **SQLite over TinyDB**: Better performance and query flexibility for growing datasets
2. **Repository Pattern**: Clean separation between data access and business logic
3. **React Query over Redux**: Better suited for server state management
4. **Recharts over Plotly**: Better React integration, smaller bundle size
5. **shadcn/ui**: Customizable components without heavy dependencies

## Migration from v1.x

If migrating from a legacy TinyDB JSON export:
```bash
cd backend
python migrations/tinydb_to_sqlite.py
```
This converts TinyDB JSON to SQLite while preserving your existing data.

---

**Version**: 2.0.0
**Architecture**: FastAPI + React + SQLite
**Last Updated**: January 2026
