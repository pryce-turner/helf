# Helf - Health & Fitness Tracker

A modern, Progressive Web App for tracking workouts, monitoring body composition, and planning training sessions. Built with FastAPI, React, and SQLite.

## Features

### 💪 Workout Tracking
- **Calendar View** - Visual overview of all workout dates with activity indicators
- **Workout Logging** - Clean, intuitive interface for logging exercises
- **Exercise Management** - Category-based organization with recent history
- **CRUD Operations** - Create, edit, reorder, and delete workout entries
- **Smart Forms** - Form persistence and auto-fill from recent sets

### 📊 Progression Tracking
- **1RM Estimation** - Automatic calculation using validated formulas
- **Interactive Charts** - Track progress over time with Recharts
- **Moving Averages** - Configurable smoothing for trend analysis
- **Future Projections** - Visualize upcoming planned workouts
- **Main Lifts** - Quick access to bench, squat, deadlift progression

### 📅 Workout Planning
- **Session Management** - Organize upcoming workouts by session
- **Bulk Import** - Import multiple workouts at once
- **Easy Transfer** - Move planned workouts to historical with one click
- **Wendler 5/3/1 Support** - Generate periodized training plans

### ⚖️ Body Composition
- **MQTT Integration** - Automatic data from smart scales (openScale-sync compatible)
- **Comprehensive Metrics** - Weight, body fat %, muscle mass, BMI, and more
- **Trend Analysis** - Visualize changes with configurable periods
- **Statistics Dashboard** - Summary cards with current metrics
- **Weight Conversion** - Automatic kg ↔ lbs conversion

### 🚀 Modern PWA
- **Offline Support** - Works without internet connection
- **Installable** - Add to home screen on mobile/desktop
- **Service Worker** - Smart caching for fast performance
- **Responsive Design** - Optimized for all screen sizes
- **Dark Mode** - Beautiful dark theme with Tailwind CSS

## Tech Stack

### Backend
- **FastAPI** - High-performance Python web framework
- **SQLite + SQLAlchemy** - Relational database with ORM
- **Pydantic** - Data validation with type hints
- **Paho-MQTT** - Smart scale integration
- **Uvicorn** - ASGI server with multi-worker support

### Frontend
- **React 18+** - Modern UI library
- **TypeScript** - Type-safe development
- **Vite** - Lightning-fast build tool
- **shadcn/ui** - Beautiful, accessible components
- **Tailwind CSS** - Utility-first styling
- **TanStack Query** - Powerful data synchronization
- **Recharts** - Composable charting library

## Quick Start

### Using Docker Compose (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd helf
```

2. Start the application:
```bash
docker-compose up -d
```

3. Access the app at `http://localhost:30171`

Your workout data will be stored in `/mnt/fast/apps/helf/data` (configurable in docker-compose.yml).

### Manual Docker Build

```bash
# Build the image
docker build -t helf:latest .

# Run the container
docker run -d \
  --name helf-app \
  -p 30171:8080 \
  -v /your/data/path:/app/data \
  -e DATA_DIR=/app/data \
  --add-host host.docker.internal:host-gateway \
  helf:latest
```

### Local Development

**Backend**:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
python -m uvicorn app.main:app --reload --port 8000
```

**Frontend**:
```bash
cd frontend
npm install
npm run dev  # Runs on http://localhost:5173
```

## API Documentation

Once running, interactive API documentation is available at:
- **Swagger UI**: `http://localhost:30171/docs`
- **ReDoc**: `http://localhost:30171/redoc`

## Architecture

```
┌─────────────────────────────────────┐
│   Browser (Progressive Web App)     │
│   - React + TypeScript              │
│   - Service Worker (offline)        │
│   - Install Prompt                  │
└──────────────┬──────────────────────┘
               │ HTTP/REST API
               ▼
┌─────────────────────────────────────┐
│   FastAPI Server                     │
│   ┌─────────────────────────────┐   │
│   │  API Routes                 │   │
│   │  - Workouts                 │   │
│   │  - Exercises                │   │
│   │  - Progression              │   │
│   │  - Body Composition         │   │
│   │  - Upcoming Workouts        │   │
│   └─────────────────────────────┘   │
│   ┌─────────────────────────────┐   │
│   │  Business Logic             │   │
│   │  - 1RM Calculation          │   │
│   │  - Moving Averages          │   │
│   │  - Projections              │   │
│   └─────────────────────────────┘   │
│   ┌─────────────────────────────┐   │
│   │  Data Access Layer          │   │
│   │  - SQLAlchemy Repositories  │   │
│   └─────────────────────────────┘   │
└──────────────┬──────────────────────┘
               │
               ▼
        ┌──────────────┐      ┌──────────┐
        │  SQLite      │      │   MQTT   │
        │  (SQL)       │      │  Broker  │
        └──────────────┘      └──────────┘
```

## Database Schema

### SQLite Tables

**workouts**
- Historical workout data with exercise details
- Ordered by date and exercise order
- Includes weight, reps, distance, time, comments

**upcoming_workouts**
- Planned workout sessions
- Organized by session number
- Ready for transfer to historical data

**body_composition**
- Body metrics from smart scales
- Timestamped measurements
- Comprehensive body composition data

**exercises**
- Unique exercise catalog
- Category associations
- Usage statistics

**categories**
- Exercise categories (Legs, Push, Pull, etc.)

## MQTT Integration

Helf integrates with smart scales via MQTT for automatic body composition tracking.

### Configuration

In `docker-compose.yml`:
```yaml
environment:
  - MQTT_BROKER_HOST=host.docker.internal
  - MQTT_BROKER_PORT=1883
```

### Supported Topics
- `openScaleSync/measurements/last` - Latest measurement
- `openScaleSync/measurements/all` - Bulk sync

### Message Format
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

## Progressive Web App

### Features
- **Offline Mode**: Works without internet
- **Install Prompt**: Add to home screen
- **Auto-Update**: New versions install automatically
- **Service Worker**: Cache-first for assets, network-first for API
- **App Icons**: Custom app icons for all platforms

### Installation
1. Open the app in Chrome, Edge, or Safari
2. Click the install prompt (or browser's install button)
3. App will be added to your home screen/app drawer

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/app/data` | Directory for SQLite database |
| `MQTT_BROKER_HOST` | `host.docker.internal` | MQTT broker hostname |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `PRODUCTION` | `true` | Production mode flag |

### Data Migration

If migrating from an existing TinyDB JSON export:

```bash
cd backend
python migrations/tinydb_to_sqlite.py
```

This will convert your legacy data into the SQLite format while preserving backups.

## Project Structure

```
helf/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/            # API route handlers
│   │   ├── models/         # Pydantic models
│   │   ├── repositories/   # Data access layer
│   │   ├── services/       # Business logic
│   │   ├── utils/          # Helper functions
│   │   ├── config.py       # Settings
│   │   ├── database.py     # SQLAlchemy setup
│   │   └── main.py         # FastAPI app
│   ├── migrations/         # Data migration scripts
│   └── pyproject.toml      # Python dependencies
├── frontend/                # React frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── hooks/          # Custom hooks
│   │   ├── lib/            # API client, utilities
│   │   ├── pages/          # Route components
│   │   ├── types/          # TypeScript types
│   │   └── main.tsx        # Entry point
│   ├── public/             # Static assets
│   ├── package.json        # Node dependencies
│   └── vite.config.ts      # Vite + PWA config
├── data/                    # Data storage
│   └── helf.db             # SQLite database
├── Dockerfile               # Multi-stage build
├── docker-compose.yml       # Docker Compose config
└── DEPLOYMENT.md            # Deployment guide
```

## Development

### Backend Development
```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend Development
```bash
cd frontend
npm run dev
```

### Building for Production
```bash
# Frontend
cd frontend
npm run build

# Docker
docker build -t helf:latest .
```

## Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests (when implemented)
cd frontend
npm test
```

## Roadmap

- [x] Backend API (FastAPI + SQLite)
- [x] Frontend (React + TypeScript)
- [x] PWA Support (Service Worker + Manifest)
- [x] Docker Deployment
- [ ] E2E Tests (Playwright)
- [ ] Mobile Apps (React Native)
- [ ] Multi-user Support (Authentication)
- [ ] Advanced Analytics

## Migration from v1.x

The old NiceGUI version is preserved in git history. To migrate:

1. Run the migration script (see Data Migration above)
2. Deploy the new Docker image
3. Verify data integrity

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is open source and available under the MIT License.

---

**Version**: 2.0.0  
**Architecture**: FastAPI + React + SQLite  
**Built with**: TypeScript, Python, shadcn/ui, Tailwind CSS
