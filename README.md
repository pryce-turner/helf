# Helf - Health & Fitness Tracker

A simple, lightweight health and fitness tracking application built with NiceGUI and CSV-based storage. Track your workouts, monitor body composition, and plan upcoming sessions.

## Features

### Workout Tracking
- 📅 **Calendar View** - Visual overview of all workout dates
- 📝 **Workout Logging** - Easy-to-use interface for logging exercises
- 📊 **Progression Tracking** - Interactive graphs showing estimated 1RM over time
- 🔮 **Upcoming Workouts** - Plan and schedule future training sessions
- 🎯 **Category-based Exercise Organization** - Filter exercises by category

### Body Composition Tracking
- ⚖️ **MQTT Integration** - Automatic data ingestion from smart scales via MQTT (supports openScale-sync)
- 📈 **Weight Trends** - Track weight changes over time with interactive graphs
- 💪 **Body Composition** - Monitor body fat %, muscle mass, BMI, and more
- 📊 **Statistics Dashboard** - Summary cards showing current metrics and changes

### General
- 💾 **CSV Storage** - Simple, portable data format (no database required)
- 📱 **Mobile Responsive** - Works on desktop and mobile devices
- 🌙 **Dark Theme** - Easy on the eyes
- 🐳 **Docker Ready** - Easy deployment with Docker Compose

## Quick Start

### Using Docker Compose (Recommended)

1. Clone the repository:
```bash
git clone <your-repo-url>
cd helf
```

2. Start the application:
```bash
docker compose up -d
```

3. Access the app at `http://localhost:8080`

Your workout data will be stored in the `./data` directory.

### Using Docker

Build and run manually:

```bash
# Build the image
docker build -t helf .

# Run the container
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  -e DATA_DIR=/app/data \
  --name helf-app \
  helf
```

### Local Development with UV

1. Install UV (if not already installed):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Create virtual environment and install dependencies:
```bash
uv venv
uv pip install .
```

3. Run the application:
```bash
python run.py
```

4. Access the app at `http://localhost:8080`

### Local Development with pip

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install .

# Run the application
python run.py
```

## Data Schema

### Workout Log (workouts.csv)
- Date
- Exercise
- Category
- Weight
- Weight Unit
- Reps
- Distance
- Distance Unit
- Time
- Comment

### Upcoming Workouts (upcoming_workouts.csv)
- Session (numeric index)
- Exercise
- Category
- Weight
- Weight Unit
- Reps
- Distance
- Distance Unit
- Time
- Comment

## Deployment

### Environment Variables

- `DATA_DIR` - Directory for CSV files (default: current directory)
- `STORAGE_SECRET` - Secret key for NiceGUI user storage (set in workout_tracker.py)
- `MQTT_BROKER_HOST` - MQTT broker hostname (default: localhost, use `host.docker.internal` in Docker to connect to host)
- `MQTT_BROKER_PORT` - MQTT broker port (default: 1883)

### Data Persistence

When using Docker, workout data is persisted in a mounted volume. The default docker-compose.yml mounts `./data` to `/app/data` in the container.

To backup your data, simply copy the CSV files from the data directory:
```bash
cp data/*.csv /your/backup/location/
```

### MQTT Integration for Body Composition

Helf automatically connects to an MQTT broker to receive body composition measurements from smart scales (via openScale-sync or similar apps).

**Docker Setup:**
The docker-compose.yml is pre-configured to connect to a Mosquitto broker running on your host machine:
- Broker host: `host.docker.internal` (maps to host machine)
- Broker port: `1883`

**Local Development:**
When running locally (not in Docker), Helf connects to `localhost:1883` by default.

**Supported MQTT Topics:**
- `openScaleSync/measurements/last` - Latest measurement (when stepping on scale)
- `openScaleSync/measurements/all` - All measurements (when syncing from app)

**Message Format:**
```json
{
  "date": "2025-11-17T08:56-0800",
  "weight": 87.15,
  "fat": 23.8,
  "muscle": 39.1,
  "water": 50.89,
  "id": 179
}
```

The app automatically parses ISO 8601 timestamps and saves all measurements to `data/body_composition.csv`.

### Production Deployment

For production deployments:

1. Set a strong storage secret in `workout_tracker.py`
2. Use a reverse proxy (nginx, Traefik) with SSL/TLS
3. Consider setting up regular backups of the `data` directory
4. Optionally, set `reload=False` in `ui.run()` for better performance

## Testing

Run the test suite:

```bash
# With UV
uv pip install -e ".[dev]"
pytest

# With pip
pip install pytest
pytest
```

## Project Structure

```
helf/
├── app/                      # Application package
│   ├── __init__.py          # Package initialization
│   ├── workout_tracker.py   # Main UI application
│   ├── workout_data.py      # Workout data layer (CSV operations)
│   ├── body_composition_data.py  # Body composition data layer
│   └── mqtt_service.py      # MQTT client service
├── tests/                   # Test suite
│   └── test_workout_data.py
├── data/                    # Data storage (created on first run)
│   ├── workouts.csv
│   ├── upcoming_workouts.csv
│   └── body_composition.csv
├── run.py                   # Application entrypoint
├── pyproject.toml           # Project configuration
├── Dockerfile               # Production container definition
├── docker-compose.yml       # Docker Compose configuration
├── .dockerignore           # Docker build exclusions
└── README.md
```

## License

This project is open source and available under the MIT License.
