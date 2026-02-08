# Helf - Health & Fitness Tracker

A modern Progressive Web App for tracking workouts, monitoring body composition, and planning training sessions. Built with FastAPI, React, and SQLite.

## Features

### Workout Tracking
- **Calendar View** - Month view with workout count indicators and training streak
- **Day View** - Log exercises with weight, reps, distance, time, and comments
- **Drag-to-Reorder** - Reorder exercises within a session via dnd-kit drag-and-drop
- **Exercise Catalog** - Category-based organization (Push, Pull, Legs, Core, etc.)
- **Completion Tracking** - Mark individual sets as complete
- **Move/Copy** - Move or copy all workouts from one date to another
- **AMRAP Notation** - Support for "5+" style AMRAP rep notation

### Progression Tracking
- **1RM Estimation** - Automatic calculation: `(0.033 x reps x weight) + weight`
- **Interactive Charts** - Track progress over time with Recharts
- **Moving Averages** - Configurable smoothing for trend analysis
- **Future Projections** - Visualize upcoming planned workouts on the same chart
- **Main Lifts** - Quick access to Bench, Squat, Deadlift progression

### Workout Planning
- **Session Management** - Organize upcoming workouts by numbered sessions
- **Liftoscript Editor** - Custom scripting language for defining workout programs
- **Built-in Presets** - Wendler 5/3/1 and StrongLifts 5x5
- **Bulk Import** - Generate multiple sessions from a single script
- **Easy Transfer** - Move planned sessions to historical workouts with one click
- **Percentage-Based Loading** - Define weights as percentage of 1RM
- **Linear Progression** - Auto-calculate progressive overload

### Body Composition
- **MQTT Integration** - Automatic data from smart scales (openScale-sync compatible)
- **Comprehensive Metrics** - Weight, body fat %, muscle mass, BMI, water %, bone mass, visceral fat
- **Trend Charts** - Visualize changes with configurable periods (1-365 days)
- **Statistics Dashboard** - Summary cards with current values and changes
- **Manual Entry** - Add measurements manually when no scale is available

### Exercise Management
- **Browse by Category** - View exercises organized by movement category
- **Seed Database** - Generate 16 preset exercises across 6 categories
- **CRUD Operations** - Create, edit, and delete exercises and categories
- **Usage Stats** - Track how often and when each exercise was last used

### Modern PWA
- **Offline Support** - Service worker with Workbox caching strategies
- **Installable** - Add to home screen on mobile and desktop
- **Auto-Update** - New versions prompt the user to refresh
- **Responsive Design** - Desktop sidebar nav, mobile bottom nav bar
- **Dark Theme** - Dark-first design with orange accent

## Tech Stack

### Backend
- **FastAPI 0.127+** - Python web framework with auto-generated API docs
- **SQLAlchemy 2.x** - ORM with repository pattern
- **SQLite** - Embedded database
- **Pydantic v2** - Request/response validation
- **Paho-MQTT 2.1+** - Smart scale integration
- **Uvicorn** - ASGI server
- **UV** - Python package manager

### Frontend
- **React 19+** - UI framework
- **TypeScript 5.9+** - Type-safe development
- **Vite 7+** - Build tool with HMR
- **shadcn/ui** - Radix UI + Tailwind components
- **Tailwind CSS 4+** - Utility-first styling
- **TanStack Query v5** - Server state management with optimistic updates
- **React Router v7** - Client-side routing
- **Recharts 3.6+** - Data visualization
- **dnd-kit** - Drag-and-drop reordering
- **date-fns 4+** - Date formatting
- **Lucide React** - Icons

## Quick Start

### Docker Compose (Recommended)

```bash
# Clone and configure
git clone <repository-url>
cd helf
cp .env.example .env
# Edit .env to set HELF_DATA_PATH to your desired data directory

# Start
docker-compose up -d

# Access at http://localhost:30171
```

### Manual Docker Build

```bash
docker build -t helf:latest .

docker run -d \
  --name helf-app \
  -p 30171:8080 \
  -v /your/data/path:/app/data \
  -e DATA_DIR=/app/data \
  --add-host host.docker.internal:host-gateway \
  helf:latest
```

### Local Development

**Backend** (port 8000):
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --port 8000
```

**Frontend** (port 5173, proxies `/api` to backend):
```bash
cd frontend
npm install
npm run dev
```

## API Documentation

Interactive docs available when the server is running:
- **Swagger UI**: http://localhost:8000/docs (dev) or http://localhost:30171/docs (Docker)
- **ReDoc**: http://localhost:8000/redoc (dev) or http://localhost:30171/redoc (Docker)

See [backend/README.md](backend/README.md) for the full endpoint reference.

## Architecture

```
┌─────────────────────────────────────┐
│   Browser (Progressive Web App)     │
│   React 19 + TypeScript + Vite      │
│   Service Worker (Workbox)          │
│   TanStack Query (optimistic UI)    │
└──────────────┬──────────────────────┘
               │ HTTP/REST API
               ▼
┌─────────────────────────────────────┐
│   FastAPI Server                    │
│   ┌─────────────────────────────┐   │
│   │  API Routes (api/)          │   │
│   │  Workouts, Exercises,       │   │
│   │  Progression, Upcoming,     │   │
│   │  Body Composition           │   │
│   └─────────────────────────────┘   │
│   ┌─────────────────────────────┐   │
│   │  Services (services/)       │   │
│   │  Progression, MQTT, Wendler │   │
│   │  Liftoscript Parser         │   │
│   └─────────────────────────────┘   │
│   ┌─────────────────────────────┐   │
│   │  Repositories (repos/)      │   │
│   │  SQLAlchemy data access     │   │
│   └─────────────────────────────┘   │
└──────────────┬──────────────────────┘
               │
        ┌──────┴──────┐      ┌──────────┐
        │   SQLite    │      │   MQTT   │
        │   helf.db   │      │  Broker  │
        └─────────────┘      └──────────┘
```

### Layer Pattern
- **API routes** - HTTP handling only, no business logic
- **Services** - Business logic, calculations, external integrations
- **Repositories** - Database queries, auto-creates exercises/categories on reference
- **Pydantic models** - Request/response validation (separate from ORM models)
- **DB models** - SQLAlchemy table definitions with relationships

## Database

SQLite database with 5 tables: `categories`, `exercises`, `workouts`, `upcoming_workouts`, `body_composition`.

See [backend/README.md](backend/README.md) for the full schema documentation.

## MQTT Integration

Helf integrates with smart scales via MQTT for automatic body composition tracking.

### Configuration

Set in `docker-compose.yml` or environment variables:
```yaml
environment:
  - MQTT_BROKER_HOST=host.docker.internal
  - MQTT_BROKER_PORT=1883
```

### Supported Topics
- `openScaleSync/measurements/last` - Latest measurement
- `openScaleSync/measurements/all` - Bulk sync

### Message Format (openScale-sync)
```json
{
  "date": "2025-11-17T08:56-0800",
  "weight": 87.15,
  "fat": 23.8,
  "muscle": 39.1,
  "water": 50.89,
  "bmi": 24.5,
  "bone": 3.2,
  "visceral_fat": 8,
  "id": 179
}
```

### Check Status
```bash
curl http://localhost:30171/api/mqtt/status
```

## Liftoscript

A simplified scripting language for defining workout programs. Used in the Upcoming page to generate sessions.

### Syntax
```
// Squat 1RM: 315lb
// Bench Press 1RM: 225lb

## Week 1 Day 1
Squat / 3x5 65%
Bench Press / 3x5 65%
Pull Ups / 3x8 bodyweight

## Week 1 Day 2
Deadlift / 1x5 70%
Overhead Press / 5x5 95lb
```

### Features
- `## Day Name` - Session headers (each becomes a numbered session)
- `Exercise / sets x reps weight` - Exercise definitions
- Weight formats: `135lb`, `60kg`, `65%` (of 1RM), `bodyweight`
- `progress: lp(5lb)` - Linear progression
- AMRAP: `5+` notation (converted to comment)
- `// Exercise 1RM: 225lb` - Required comment for percentage-based weights
- `// Exercise SW: 135lb` - Required comment for linear progression starting weight
- Automatic kg-to-lbs conversion and rounding to nearest 5 lbs
- Multi-cycle repetition

### Built-in Presets
- **Wendler 5/3/1** - 4-week periodized program (3 days/week, main lifts + accessories)
- **StrongLifts 5x5** - A/B alternating workouts (Squat/Bench/Row and Squat/OHP/Deadlift)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HELF_DATA_PATH` | - | Host path for data volume mount |
| `DATA_DIR` | `/app/data` | Container path for SQLite database |
| `MQTT_BROKER_HOST` | `host.docker.internal` | MQTT broker hostname |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `PRODUCTION` | `true` | Production mode flag |

## Project Structure

```
helf/
├── backend/                  # FastAPI backend (see backend/README.md)
│   ├── app/
│   │   ├── api/             # Route handlers (workouts, exercises, etc.)
│   │   ├── db/models.py     # SQLAlchemy ORM models
│   │   ├── models/          # Pydantic request/response schemas
│   │   ├── repositories/    # Data access layer
│   │   ├── services/        # Business logic (progression, MQTT, Liftoscript)
│   │   ├── utils/           # Helpers (1RM calc, date handling)
│   │   ├── presets/         # Built-in workout programs (.liftoscript files)
│   │   ├── config.py        # Settings (env vars)
│   │   ├── database.py      # SQLAlchemy engine/session
│   │   └── main.py          # FastAPI app entry
│   ├── migrations/          # Data migration scripts
│   ├── tests/               # Pytest test suite (18 test files)
│   └── pyproject.toml       # Python dependencies
├── frontend/                 # React frontend (see frontend/README.md)
│   ├── src/
│   │   ├── components/      # Navigation, LiftoscriptEditor, PWA, ui/
│   │   ├── hooks/           # React Query hooks (useWorkouts, etc.)
│   │   ├── lib/api.ts       # Axios API client
│   │   ├── pages/           # Calendar, WorkoutSession, Progression, etc.
│   │   ├── types/           # TypeScript type definitions
│   │   ├── App.tsx          # Router + QueryClient
│   │   ├── main.tsx         # Entry point + SW registration
│   │   └── index.css        # Design system (CSS custom properties)
│   ├── public/              # PWA icons, static assets
│   ├── package.json
│   └── vite.config.ts       # Vite + PWA + proxy config
├── data/                     # SQLite database (gitignored)
├── Dockerfile                # Multi-stage build (Node + Python)
├── docker-compose.yml        # Single-service deployment
├── .env.example              # Environment template
└── LICENSE                   # MIT License
```

## Testing

```bash
# Backend tests (pytest, in-memory SQLite)
cd backend
pytest
pytest -v                                    # verbose
pytest tests/test_services_liftoscript.py    # specific file
pytest --cov=app                             # coverage

# Frontend linting
cd frontend
npm run lint

# Frontend type check + build
npm run build
```

## Development

### Backend
```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm run dev
```

### Building for Production
```bash
# Frontend build
cd frontend
npm run build

# Docker image
docker build -t helf:latest .
```

## Data Migration

If migrating from the legacy TinyDB/NiceGUI v1.x:

```bash
cd backend
python migrations/tinydb_to_sqlite.py
```

This converts TinyDB JSON exports to the SQLite schema. The old NiceGUI version is preserved in git history.

## Roadmap

- [x] Backend API (FastAPI + SQLite)
- [x] Frontend (React + TypeScript)
- [x] PWA Support (Service Worker + Manifest)
- [x] Docker Deployment
- [x] Liftoscript workout program language
- [x] Drag-and-drop exercise reordering
- [x] Exercise catalog with seed data
- [ ] E2E Tests (Playwright)
- [ ] Multi-user Support (Authentication)
- [ ] Advanced Analytics

## License

This project is open source and available under the [MIT License](LICENSE).

---

**Version**: 2.0.0
**Architecture**: FastAPI + React 19 + SQLite
**Built with**: TypeScript, Python, shadcn/ui, Tailwind CSS 4
