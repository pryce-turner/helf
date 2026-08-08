# Helf Refactoring Plan: NiceGUI → FastAPI + React + shadcn/ui + TinyDB

## Executive Summary

This document outlines a comprehensive plan to refactor the Helf health tracking application from a NiceGUI monolith with CSV-based storage to a modern PWA architecture using:
- **Backend**: FastAPI (REST API)
- **Frontend**: React + Vite + TypeScript
- **UI Library**: shadcn/ui (Tailwind CSS + Radix UI)
- **Database**: TinyDB (JSON-based document store)
- **PWA**: Service workers, manifest, offline support

## Current Application Analysis

### Technology Stack (Current)
- **Framework**: NiceGUI (Python-based reactive UI framework)
- **Server**: Uvicorn (via NiceGUI)
- **Storage**: CSV files (workouts.csv, body_composition.csv, upcoming_workouts.csv)
- **External Integration**: MQTT (Paho-MQTT) for smart scale data
- **Charts**: Plotly
- **Deployment**: Docker + Docker Compose

### Feature Inventory

#### 1. Workout Tracking (`/day/{date}`)
- **Calendar view** with workout count indicators
- **Session logging** with exercise selection
- **Exercise management**:
  - Category-based organization
  - Custom exercise/category creation
  - Recent sets history display
- **Set tracking**:
  - Weight (lbs/kg)
  - Reps (including AMRAP notation like "5+")
  - Optional: Distance, Time, Comments
  - Order management (reorder exercises within a session)
- **CRUD operations**: Create, Edit, Update, Delete workouts
- **Form UX features**:
  - Smart form persistence (keeps weight/reps between sets)
  - Optional fields toggle
  - Recent exercise history

#### 2. Progression Tracking (`/progression/{exercise}`)
- **Main lifts tracking**: Bench, Squat, Deadlift
- **Custom exercise selection**
- **1RM estimation** using formula: `(0.033 × reps × weight) + weight`
- **Historical data visualization**:
  - Scatter plot of estimated 1RM over time
  - Configurable moving average (default 30 days)
  - Hover tooltips with set details
- **Future projection**:
  - Projects upcoming workouts onto timeline
  - 1 day on, 1 day off schedule
  - Visual separation (today marker)

#### 3. Upcoming Workouts (`/upcoming`)
- **Session-based planning**
- **Bulk workout import** from CSV
- **Session transfer** to historical data
- **Wendler 5/3/1 generator** (separate utility)
  - Automated progression calculation
  - Multi-cycle planning
  - AMRAP set notation
  - Deload weeks

#### 4. Body Composition (`/body-composition`)
- **MQTT integration**:
  - Real-time data from smart scales
  - OpenScale-sync format support
  - Auto-deduplication by timestamp
- **Metrics tracked**:
  - Weight (kg → lbs conversion for display)
  - Body fat %
  - Muscle mass
  - Water %
  - BMI, Bone mass, Visceral fat, Metabolic age, Protein %
- **Analytics**:
  - 30-day moving average weight change
  - Trend visualization
  - Summary statistics cards
  - Configurable MA period (default 7 days)

#### 5. Data Management
- **CSV schema**:
  ```
  workouts.csv: Date, Exercise, Category, Weight, Weight Unit, Reps, 
                Distance, Distance Unit, Time, Comment, Order
  
  upcoming_workouts.csv: Session, Exercise, Category, Weight, Weight Unit,
                         Reps, Distance, Distance Unit, Time, Comment
  
  body_composition.csv: Timestamp, Date, Weight, Weight Unit, Body Fat %,
                        Muscle Mass, BMI, Water %, Bone Mass, Visceral Fat,
                        Metabolic Age, Protein %
  ```
- **Data operations**:
  - Append-only writes
  - Deduplication (body comp by timestamp)
  - Order management (workout sessions)
  - Date-based filtering

### Architecture (Current)

```
┌─────────────────────────────────────────┐
│         NiceGUI Application             │
│  (Reactive UI + Server in one process)  │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────┐  ┌─────────────────┐ │
│  │ UI Pages     │  │ Data Modules    │ │
│  │ - Calendar   │  │ - workout_data  │ │
│  │ - Session    │  │ - body_comp_data│ │
│  │ - Progression│  │ - mqtt_service  │ │
│  │ - Upcoming   │  │                 │ │
│  │ - Body Comp  │  │                 │ │
│  └──────────────┘  └─────────────────┘ │
│                                         │
└─────────────────────────────────────────┘
           │                  │
           ▼                  ▼
    ┌──────────┐      ┌──────────┐
    │ CSV Files│      │   MQTT   │
    └──────────┘      │  Broker  │
                      └──────────┘
```

## Target Architecture

### Technology Stack (New)

#### Backend
- **Framework**: FastAPI 0.115+
- **Database**: TinyDB 4.8+
- **MQTT**: Paho-MQTT 2.0+
- **Validation**: Pydantic v2
- **Server**: Uvicorn with standard workers
- **CORS**: FastAPI middleware

#### Frontend
- **Build Tool**: Vite 6+
- **Framework**: React 18+
- **Language**: TypeScript 5+
- **UI Library**: shadcn/ui (latest)
- **Styling**: Tailwind CSS 4+
- **Icons**: Lucide React
- **Charts**: Recharts or Chart.js
- **State**: TanStack Query (React Query) v5
- **Routing**: React Router v7
- **Forms**: React Hook Form + Zod
- **Date Handling**: date-fns
- **HTTP Client**: Axios or native fetch

#### PWA
- **Service Worker**: Workbox 7+
- **Manifest**: Web App Manifest
- **Offline**: Cache-first strategies
- **Install**: Add to home screen support

#### Development
- **Package Manager**: pnpm or npm
- **Linting**: ESLint + Prettier
- **Type Checking**: TypeScript strict mode
- **Testing**: Vitest (backend), Playwright (e2e)

### New Architecture Diagram

```
┌──────────────────────────────────────────────────────┐
│                   Frontend (React)                   │
│  ┌────────────────────────────────────────────────┐  │
│  │  Routes (React Router)                         │  │
│  │  - /calendar                                   │  │
│  │  - /day/:date                                  │  │
│  │  - /progression/:exercise?                     │  │
│  │  - /upcoming                                   │  │
│  │  - /body-composition                           │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │  Components (shadcn/ui + custom)               │  │
│  │  - Calendar, WorkoutForm, ExerciseChart        │  │
│  │  - ProgressionGraph, BodyCompDashboard         │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │  State Management (React Query)                │  │
│  │  - API queries, mutations, cache               │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │  PWA (Service Worker + Manifest)               │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                         │
                         │ REST API (JSON)
                         ▼
┌──────────────────────────────────────────────────────┐
│                Backend (FastAPI)                     │
│  ┌────────────────────────────────────────────────┐  │
│  │  API Routes                                    │  │
│  │  - /api/workouts                               │  │
│  │  - /api/exercises                              │  │
│  │  - /api/categories                             │  │
│  │  - /api/upcoming                               │  │
│  │  - /api/body-composition                       │  │
│  │  - /api/progression/{exercise}                 │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │  Business Logic (Services)                     │  │
│  │  - WorkoutService, BodyCompService             │  │
│  │  - ProgressionService, MQTTService             │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │  Data Access Layer (Repositories)              │  │
│  │  - TinyDB queries, indexes, caching            │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
           │                          │
           ▼                          ▼
    ┌──────────┐              ┌──────────┐
    │ TinyDB   │              │   MQTT   │
    │ (JSON)   │              │  Broker  │
    └──────────┘              └──────────┘
```

## Database Migration: CSV → TinyDB

### TinyDB Schema Design

TinyDB is a document-oriented database that stores data as JSON. Each table is a collection of documents.

#### Table: `workouts`
```json
{
  "doc_id": 1,
  "date": "2025-11-17",
  "exercise": "Barbell Squat",
  "category": "Legs",
  "weight": 245,
  "weight_unit": "lbs",
  "reps": 5,
  "distance": null,
  "distance_unit": null,
  "time": null,
  "comment": "Week 1 - Set 2",
  "order": 2,
  "created_at": "2025-11-17T14:30:00-08:00",
  "updated_at": "2025-11-17T14:30:00-08:00"
}
```

**Indexes**: `date`, `exercise`, `category`

#### Table: `upcoming_workouts`
```json
{
  "doc_id": 1,
  "session": 1,
  "exercise": "Barbell Squat",
  "category": "Legs",
  "weight": 225,
  "weight_unit": "lbs",
  "reps": "5+",
  "distance": null,
  "distance_unit": null,
  "time": null,
  "comment": "Week 1 - Set 1 AMRAP",
  "created_at": "2025-11-01T10:00:00-08:00"
}
```

**Indexes**: `session`

#### Table: `body_composition`
```json
{
  "doc_id": 1,
  "timestamp": "2025-11-17T16:56:00-08:00",
  "date": "2025-11-17",
  "weight": 87.15,
  "weight_unit": "kg",
  "body_fat_pct": 23.8,
  "muscle_mass": 39.1,
  "bmi": null,
  "water_pct": 50.89,
  "bone_mass": null,
  "visceral_fat": null,
  "metabolic_age": null,
  "protein_pct": null,
  "created_at": "2025-11-17T16:56:00-08:00"
}
```

**Indexes**: `timestamp` (unique), `date`

#### Table: `exercises`
```json
{
  "doc_id": 1,
  "name": "Barbell Squat",
  "category": "Legs",
  "last_used": "2025-11-17",
  "use_count": 150,
  "created_at": "2018-04-01T00:00:00-08:00"
}
```

**Indexes**: `name` (unique), `category`

#### Table: `categories`
```json
{
  "doc_id": 1,
  "name": "Legs",
  "created_at": "2018-04-01T00:00:00-08:00"
}
```

**Indexes**: `name` (unique)

### Migration Strategy

1. **Create migration script** (`migrate_csv_to_tinydb.py`)
   - Read all CSV files
   - Parse and validate data
   - Insert into TinyDB with proper schema
   - Preserve timestamps and ordering
   - Create indexes
   - Generate migration report

2. **Data transformation**:
   - Convert date strings to ISO 8601 format
   - Normalize units (keep as-is, convert in business layer)
   - Handle missing/null values
   - Generate UUIDs if needed
   - Extract unique exercises/categories

3. **Validation**:
   - Row count verification
   - Spot-check random samples
   - Verify date ranges
   - Check for duplicates

4. **Backup strategy**:
   - Keep CSV files as backup
   - Export TinyDB to JSON for version control
   - Rollback capability

## API Design

### REST Endpoints

#### Workouts

```
GET    /api/workouts                  # List all workouts (with pagination)
GET    /api/workouts?date=YYYY-MM-DD  # Get workouts by date
GET    /api/workouts/:id              # Get single workout
POST   /api/workouts                  # Create workout
PUT    /api/workouts/:id              # Update workout
DELETE /api/workouts/:id              # Delete workout
PATCH  /api/workouts/:id/reorder      # Reorder workout (up/down)

GET    /api/workouts/calendar         # Get workout counts by date
        ?year=2025&month=11
```

#### Exercises & Categories

```
GET    /api/exercises                 # List all exercises
GET    /api/exercises/:name           # Get exercise details
POST   /api/exercises                 # Create exercise
GET    /api/exercises/recent          # Recently used exercises
        ?limit=10

GET    /api/categories                # List all categories
POST   /api/categories                # Create category
GET    /api/categories/:name/exercises # Get exercises in category
```

#### Progression

```
GET    /api/progression/:exercise     # Get progression data
        ?include_upcoming=true
GET    /api/progression/main-lifts    # Get data for main 3 lifts
```

#### Upcoming Workouts

```
GET    /api/upcoming                  # Get all upcoming workouts
GET    /api/upcoming/session/:num     # Get specific session
POST   /api/upcoming                  # Add upcoming workout
DELETE /api/upcoming/session/:num     # Delete session
POST   /api/upcoming/session/:num/transfer  # Transfer to date
        { "date": "2025-11-18" }
POST   /api/upcoming/bulk             # Bulk import (Wendler generator)
```

#### Body Composition

```
GET    /api/body-composition          # List all measurements
        ?start_date=&end_date=&limit=
GET    /api/body-composition/latest   # Latest measurement
GET    /api/body-composition/stats    # Summary statistics
POST   /api/body-composition          # Create measurement (manual)
DELETE /api/body-composition/:id      # Delete measurement

GET    /api/body-composition/trends   # Trend data for charts
        ?days=30&metric=weight
```

#### MQTT Status

```
GET    /api/mqtt/status               # Connection status
POST   /api/mqtt/reconnect            # Trigger reconnect
```

### Request/Response Examples

#### POST /api/workouts
```json
Request:
{
  "date": "2025-11-18",
  "exercise": "Barbell Squat",
  "category": "Legs",
  "weight": 245,
  "weight_unit": "lbs",
  "reps": 5,
  "comment": "Felt strong today"
}

Response: 201 Created
{
  "id": 123,
  "date": "2025-11-18",
  "exercise": "Barbell Squat",
  "category": "Legs",
  "weight": 245,
  "weight_unit": "lbs",
  "reps": 5,
  "distance": null,
  "distance_unit": null,
  "time": null,
  "comment": "Felt strong today",
  "order": 1,
  "created_at": "2025-11-18T10:30:00-08:00",
  "updated_at": "2025-11-18T10:30:00-08:00"
}
```

#### GET /api/progression/Barbell%20Squat
```json
Response: 200 OK
{
  "exercise": "Barbell Squat",
  "historical": [
    {
      "date": "2025-11-17",
      "weight": 285,
      "weight_unit": "lbs",
      "reps": "5+",
      "estimated_1rm": 332.0,
      "comment": "Week 1 - Set 3 AMRAP"
    }
  ],
  "upcoming": [
    {
      "session": 4,
      "projected_date": "2025-11-19",
      "weight": 205,
      "weight_unit": "lbs",
      "reps": 3,
      "estimated_1rm": 225.5,
      "comment": "Week 2 - Set 1"
    }
  ]
}
```

## Frontend Architecture

### Project Structure

```
frontend/
├── public/
│   ├── manifest.json           # PWA manifest
│   ├── icons/                  # App icons (various sizes)
│   └── service-worker.js       # Service worker (generated)
├── src/
│   ├── main.tsx                # Entry point
│   ├── App.tsx                 # Root component
│   ├── routes/                 # Route components
│   │   ├── Calendar.tsx
│   │   ├── WorkoutSession.tsx
│   │   ├── Progression.tsx
│   │   ├── Upcoming.tsx
│   │   └── BodyComposition.tsx
│   ├── components/             # Reusable components
│   │   ├── ui/                 # shadcn/ui components
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── input.tsx
│   │   │   ├── select.tsx
│   │   │   ├── calendar.tsx
│   │   │   └── ...
│   │   ├── Calendar/
│   │   │   ├── CalendarGrid.tsx
│   │   │   └── DayCell.tsx
│   │   ├── Workout/
│   │   │   ├── WorkoutForm.tsx
│   │   │   ├── WorkoutTable.tsx
│   │   │   ├── ExerciseSelect.tsx
│   │   │   └── RecentSets.tsx
│   │   ├── Charts/
│   │   │   ├── ProgressionChart.tsx
│   │   │   ├── BodyCompChart.tsx
│   │   │   └── MovingAverage.tsx
│   │   └── Layout/
│   │       ├── Navigation.tsx
│   │       └── Header.tsx
│   ├── lib/
│   │   ├── api.ts              # API client
│   │   ├── utils.ts            # Utility functions
│   │   ├── constants.ts        # App constants
│   │   └── calculations.ts     # 1RM, moving avg, etc.
│   ├── hooks/                  # Custom React hooks
│   │   ├── useWorkouts.ts
│   │   ├── useProgression.ts
│   │   ├── useBodyComp.ts
│   │   └── usePWA.ts
│   ├── types/                  # TypeScript types
│   │   ├── workout.ts
│   │   ├── exercise.ts
│   │   ├── bodyComp.ts
│   │   └── api.ts
│   ├── styles/
│   │   └── globals.css         # Global styles + Tailwind
│   └── vite-env.d.ts
├── index.html
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
├── package.json
└── pnpm-lock.yaml
```

### Key Components

#### Calendar Component
```tsx
// CalendarGrid.tsx
interface WorkoutCount {
  [date: string]: number;
}

export function CalendarGrid({ year, month, workoutCounts }: Props) {
  // Render calendar with workout indicators
  // Click handler navigates to /day/:date
}
```

#### Workout Form Component
```tsx
// WorkoutForm.tsx
export function WorkoutForm({ date, editingWorkout, onSuccess }: Props) {
  const form = useForm<WorkoutFormData>({
    resolver: zodResolver(workoutSchema)
  });
  
  const { data: exercises } = useExercises();
  const { data: recentSets } = useRecentSets(form.watch('exercise'));
  const mutation = useCreateWorkout();
  
  // Form with category/exercise selection
  // Optional fields toggle
  // Recent sets display
  // Submit handler
}
```

#### Progression Chart Component
```tsx
// ProgressionChart.tsx
export function ProgressionChart({ exercise, maWindow }: Props) {
  const { data } = useProgression(exercise);
  
  // Recharts scatter plot + line chart
  // Historical + upcoming data
  // Moving average calculation
  // Today marker
}
```

### State Management with React Query

```tsx
// hooks/useWorkouts.ts
export function useWorkouts(date?: string) {
  return useQuery({
    queryKey: ['workouts', date],
    queryFn: () => api.getWorkouts({ date }),
  });
}

export function useCreateWorkout() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.createWorkout,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['workouts', data.date] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
    },
  });
}
```

### PWA Configuration

#### manifest.json
```json
{
  "name": "Helf - Health & Fitness Tracker",
  "short_name": "Helf",
  "description": "Track workouts, progression, and body composition",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#1a1a1a",
  "theme_color": "#3b82f6",
  "icons": [
    {
      "src": "/icons/icon-192x192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/icons/icon-512x512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

#### Service Worker Strategy
- **Cache-first**: Static assets (HTML, CSS, JS, icons)
- **Network-first**: API calls (with fallback to cache)
- **Background sync**: Queue mutations when offline
- **Cache invalidation**: On app update

## Backend Implementation Details

### Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app entry
│   ├── config.py               # Configuration
│   ├── database.py             # TinyDB setup
│   ├── models/                 # Pydantic models
│   │   ├── workout.py
│   │   ├── exercise.py
│   │   ├── body_comp.py
│   │   └── upcoming.py
│   ├── repositories/           # Data access layer
│   │   ├── workout_repo.py
│   │   ├── exercise_repo.py
│   │   ├── body_comp_repo.py
│   │   └── upcoming_repo.py
│   ├── services/               # Business logic
│   │   ├── workout_service.py
│   │   ├── progression_service.py
│   │   ├── body_comp_service.py
│   │   └── mqtt_service.py
│   ├── api/                    # API routes
│   │   ├── workouts.py
│   │   ├── exercises.py
│   │   ├── progression.py
│   │   ├── upcoming.py
│   │   └── body_comp.py
│   └── utils/
│       ├── calculations.py     # 1RM, moving avg
│       ├── date_helpers.py
│       └── validators.py
├── migrations/
│   └── csv_to_tinydb.py        # Migration script
├── tests/
│   ├── test_api/
│   ├── test_services/
│   └── test_repositories/
├── pyproject.toml
└── README.md
```

### FastAPI Application Setup

```python
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import workouts, exercises, progression, upcoming, body_comp
from app.services.mqtt_service import MQTTService

app = FastAPI(title="Helf API", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(workouts.router, prefix="/api/workouts", tags=["workouts"])
app.include_router(exercises.router, prefix="/api/exercises", tags=["exercises"])
app.include_router(progression.router, prefix="/api/progression", tags=["progression"])
app.include_router(upcoming.router, prefix="/api/upcoming", tags=["upcoming"])
app.include_router(body_comp.router, prefix="/api/body-composition", tags=["body-composition"])

# Serve frontend static files in production
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# Startup: Initialize MQTT service
mqtt_service = None

@app.on_event("startup")
async def startup():
    global mqtt_service
    mqtt_service = MQTTService()
    mqtt_service.start()

@app.on_event("shutdown")
async def shutdown():
    if mqtt_service:
        mqtt_service.stop()
```

### TinyDB Setup

```python
# database.py
from tinydb import TinyDB, Query
from tinydb.middlewares import CachingMiddleware
from tinydb.storages import JSONStorage
from pathlib import Path
import os

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DB_PATH = DATA_DIR / "helf.json"

# Initialize database with caching
db = TinyDB(DB_PATH, storage=CachingMiddleware(JSONStorage))

# Tables
workouts_table = db.table('workouts')
upcoming_table = db.table('upcoming_workouts')
body_comp_table = db.table('body_composition')
exercises_table = db.table('exercises')
categories_table = db.table('categories')

def get_db():
    return db

def close_db():
    db.close()
```

### Example Repository

```python
# repositories/workout_repo.py
from tinydb import Query
from app.database import workouts_table
from app.models.workout import Workout, WorkoutCreate
from datetime import datetime
from typing import List, Optional

class WorkoutRepository:
    def __init__(self):
        self.table = workouts_table
        self.query = Query()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[dict]:
        all_workouts = self.table.all()
        return all_workouts[skip:skip+limit]
    
    def get_by_date(self, date: str) -> List[dict]:
        return self.table.search(self.query.date == date)
    
    def get_by_id(self, doc_id: int) -> Optional[dict]:
        return self.table.get(doc_id=doc_id)
    
    def create(self, workout: WorkoutCreate) -> dict:
        workout_dict = workout.model_dump()
        workout_dict['created_at'] = datetime.now().isoformat()
        workout_dict['updated_at'] = datetime.now().isoformat()
        
        # Auto-assign order
        date_workouts = self.get_by_date(workout.date)
        workout_dict['order'] = len(date_workouts) + 1
        
        doc_id = self.table.insert(workout_dict)
        return self.table.get(doc_id=doc_id)
    
    def update(self, doc_id: int, workout: WorkoutCreate) -> Optional[dict]:
        workout_dict = workout.model_dump()
        workout_dict['updated_at'] = datetime.now().isoformat()
        
        self.table.update(workout_dict, doc_ids=[doc_id])
        return self.table.get(doc_id=doc_id)
    
    def delete(self, doc_id: int) -> bool:
        return len(self.table.remove(doc_ids=[doc_id])) > 0
    
    def get_workout_counts_by_date(self, year: int, month: int) -> dict:
        # Get all workouts for the month
        workouts = self.table.search(
            self.query.date.matches(f'{year}-{month:02d}-.*')
        )
        
        counts = {}
        for workout in workouts:
            date = workout['date']
            counts[date] = counts.get(date, 0) + 1
        
        return counts
```

### Example API Route

```python
# api/workouts.py
from fastapi import APIRouter, HTTPException, Query as QueryParam
from typing import List, Optional
from app.models.workout import Workout, WorkoutCreate
from app.repositories.workout_repo import WorkoutRepository

router = APIRouter()
repo = WorkoutRepository()

@router.get("/", response_model=List[Workout])
def get_workouts(
    date: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
):
    if date:
        return repo.get_by_date(date)
    return repo.get_all(skip=skip, limit=limit)

@router.post("/", response_model=Workout, status_code=201)
def create_workout(workout: WorkoutCreate):
    return repo.create(workout)

@router.get("/calendar")
def get_calendar(year: int, month: int):
    counts = repo.get_workout_counts_by_date(year, month)
    return {"year": year, "month": month, "counts": counts}

@router.put("/{workout_id}", response_model=Workout)
def update_workout(workout_id: int, workout: WorkoutCreate):
    updated = repo.update(workout_id, workout)
    if not updated:
        raise HTTPException(status_code=404, detail="Workout not found")
    return updated

@router.delete("/{workout_id}", status_code=204)
def delete_workout(workout_id: int):
    deleted = repo.delete(workout_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workout not found")
```

## Migration Plan: Step-by-Step

### Phase 1: Setup & Infrastructure (Week 1)

1. **Backend Setup**
   - [ ] Create new project structure
   - [ ] Install FastAPI, TinyDB, dependencies
   - [ ] Configure development environment
   - [ ] Set up linting, formatting

2. **Database Migration**
   - [ ] Write CSV → TinyDB migration script
   - [ ] Test migration with sample data
   - [ ] Run full migration
   - [ ] Verify data integrity

3. **Frontend Setup**
   - [ ] Initialize Vite + React + TypeScript
   - [ ] Install shadcn/ui, Tailwind, dependencies
   - [ ] Configure build tools
   - [ ] Set up routing structure

### Phase 2: Backend Core (Week 2)

1. **Database Layer**
   - [ ] Define TinyDB tables and indexes
   - [ ] Implement repositories (workouts, exercises, body comp, upcoming)
   - [ ] Write unit tests

2. **API Implementation**
   - [ ] Implement workout endpoints
   - [ ] Implement exercise/category endpoints
   - [ ] Implement progression endpoints
   - [ ] Implement upcoming endpoints
   - [ ] Implement body composition endpoints
   - [ ] Write API tests

3. **Business Logic**
   - [ ] Port 1RM calculation
   - [ ] Port moving average calculation
   - [ ] Port progression projection logic
   - [ ] Implement MQTT service for TinyDB

### Phase 3: Frontend Core (Week 3)

1. **shadcn/ui Components**
   - [ ] Install base components (button, card, input, etc.)
   - [ ] Customize theme
   - [ ] Create layout components

2. **API Client**
   - [ ] Implement API client with TypeScript
   - [ ] Set up React Query
   - [ ] Create custom hooks for each resource

3. **Core Routes**
   - [ ] Calendar page
   - [ ] Workout session page
   - [ ] Progression page
   - [ ] Upcoming workouts page
   - [ ] Body composition page

### Phase 4: Feature Parity (Week 4)

1. **Workout Tracking**
   - [ ] Calendar grid with workout counts
   - [ ] Workout form with validation
   - [ ] Exercise/category selection
   - [ ] Recent sets history
   - [ ] CRUD operations
   - [ ] Reordering

2. **Progression Tracking**
   - [ ] Main lifts charts
   - [ ] Custom exercise selection
   - [ ] Moving average configuration
   - [ ] Historical + upcoming visualization

3. **Body Composition**
   - [ ] Summary statistics cards
   - [ ] Trend charts
   - [ ] MQTT integration testing

4. **Upcoming Workouts**
   - [ ] Session view
   - [ ] Transfer to historical
   - [ ] Bulk import UI

### Phase 5: PWA & Polish (Week 5)

1. **PWA Implementation**
   - [ ] Create manifest.json
   - [ ] Generate icons
   - [ ] Implement service worker
   - [ ] Test offline functionality
   - [ ] Test install flow

2. **UX Enhancements**
   - [ ] Loading states
   - [ ] Error handling
   - [ ] Toast notifications
   - [ ] Form validation feedback
   - [ ] Responsive design testing

3. **Performance**
   - [ ] Code splitting
   - [ ] Lazy loading
   - [ ] Query caching optimization
   - [ ] Bundle size analysis

### Phase 6: Testing & Deployment (Week 6)

1. **Testing**
   - [ ] Backend unit tests (>80% coverage)
   - [ ] Frontend component tests
   - [ ] E2E tests with Playwright
   - [ ] Mobile device testing

2. **Deployment**
   - [ ] Update Dockerfile for FastAPI + React
   - [ ] Configure nginx for SPA routing
   - [ ] Update docker-compose.yml
   - [ ] Environment variable configuration
   - [ ] Test production build

3. **Documentation**
   - [ ] Update README with new architecture
   - [ ] API documentation (OpenAPI/Swagger)
   - [ ] Migration guide for users
   - [ ] Developer setup guide

## Docker Configuration

### New Dockerfile

```dockerfile
# Multi-stage build for FastAPI + React

# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Build backend
FROM python:3.12-slim AS backend-build

WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY backend/pyproject.toml backend/README.md ./
RUN uv pip install --system --no-cache .

# Stage 3: Production
FROM python:3.12-slim AS production

WORKDIR /app

# Copy Python dependencies
COPY --from=backend-build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy backend code
COPY backend/app /app/app

# Copy frontend build
COPY --from=frontend-build /app/frontend/dist /app/static

# Create data directory
RUN mkdir -p /app/data

ENV DATA_DIR=/app/data \
    PYTHONPATH=/app \
    PRODUCTION=true

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health').read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]
```

### Updated docker-compose.yml

```yaml
services:
  helf:
    build: .
    container_name: helf-app
    ports:
      - "30171:8080"
    volumes:
      - /mnt/fast/apps/helf/data:/app/data
    environment:
      - DATA_DIR=/app/data
      - MQTT_BROKER_HOST=host.docker.internal
      - MQTT_BROKER_PORT=1883
      - CORS_ORIGINS=*
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
```

## Risk Mitigation

### Data Safety
- **Backup strategy**: Keep CSV files as backup during migration
- **Rollback plan**: Script to convert TinyDB → CSV if needed
- **Validation**: Automated tests to verify data integrity

### Breaking Changes
- **API versioning**: Start with v2 API endpoints
- **Feature flags**: Ability to toggle new features
- **Gradual rollout**: Test with subset of data first

### Performance Concerns
- **TinyDB limitations**: For large datasets (>100k records), consider migration path to SQLite
- **Caching**: Implement in-memory caching for frequently accessed data
- **Pagination**: All list endpoints support pagination

### MQTT Integration
- **Testing**: Set up local Mosquitto broker for testing
- **Reconnection logic**: Handle broker disconnections gracefully
- **Message queue**: Queue messages when offline

## Future Enhancements (Post-MVP)

1. **Authentication & Multi-user**
   - User accounts
   - JWT authentication
   - Per-user data isolation

2. **Advanced Analytics**
   - Workout volume tracking
   - Periodization planning
   - Predictive analytics

3. **Mobile Apps**
   - React Native app using same API
   - Native iOS/Android apps

4. **Social Features**
   - Share workouts
   - Compare progress with friends
   - Leaderboards

5. **Integration Ecosystem**
   - Strava integration
   - Google Fit / Apple Health
   - Other fitness apps

6. **Database Migration**
   - Move from TinyDB to PostgreSQL for scalability
   - GraphQL API option

## Success Criteria

### Technical
- ✅ All current features implemented
- ✅ API response time < 200ms (95th percentile)
- ✅ PWA installable on mobile devices
- ✅ Offline functionality working
- ✅ Test coverage > 80%
- ✅ Zero data loss during migration

### User Experience
- ✅ Faster page loads (< 2s initial load)
- ✅ Smoother interactions (no page reloads)
- ✅ Mobile-first responsive design
- ✅ Works offline
- ✅ No regression in features

### Developer Experience
- ✅ Clear separation of concerns
- ✅ Type safety (TypeScript + Pydantic)
- ✅ Easy to add new features
- ✅ Comprehensive documentation
- ✅ CI/CD pipeline

## Timeline Summary

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1: Setup | 1 week | Project structure, migration script, dev environment |
| Phase 2: Backend | 1 week | API implementation, repositories, tests |
| Phase 3: Frontend | 1 week | React app, API client, base components |
| Phase 4: Features | 1 week | All features at parity with current app |
| Phase 5: PWA | 1 week | PWA functionality, UX polish |
| Phase 6: Deploy | 1 week | Testing, documentation, production deployment |

**Total: 6 weeks**

## Conclusion

This refactoring will transform Helf from a monolithic NiceGUI application into a modern, scalable PWA with clean separation between frontend and backend. The new architecture will provide:

- **Better UX**: Faster, smoother, works offline
- **Better DX**: Type-safe, modular, testable
- **Better Scalability**: API-first, database-backed, cloud-ready
- **Better Maintainability**: Clear structure, modern tooling

The migration is designed to be low-risk with data validation at every step and the ability to roll back if needed.
