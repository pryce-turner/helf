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

2. Install dependencies:
```bash
uv pip install -e .
```

3. Run the application:
```bash
python workout_tracker.py
```

4. Access the app at `http://localhost:8080`

### Local Development with pip

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install nicegui plotly

# Run the application
python workout_tracker.py
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
- `openScaleSync/measurements/insert` - New measurements
- `openScaleSync/measurements/update` - Updated measurements

**Message Format:**
```json
{
  "date": 1572082380000,
  "weight": 80.0,
  "fat": 18.5,
  "muscle": 45.2,
  "bmi": 24.8
}
```

The app will automatically save measurements to `data/body_composition.csv` when received.

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
├── workout_tracker.py       # Main UI application
├── workout_data.py          # Data layer (CSV operations)
├── test_workout_data.py     # Test suite
├── pyproject.toml           # Project configuration
├── Dockerfile               # Container definition
├── docker-compose.yml       # Docker Compose configuration
├── .dockerignore           # Docker build exclusions
├── data/                   # Workout data (created on first run)
│   ├── workouts.csv
│   └── upcoming_workouts.csv
└── README.md
```

## License

This project is open source and available under the MIT License.
