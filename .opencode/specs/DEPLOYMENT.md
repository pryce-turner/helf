# Helf Deployment Guide

## Prerequisites

- Docker and Docker Compose installed
- Port 30171 available on host
- (Optional) MQTT broker running on host for smart scale integration

## Quick Start

### 1. Clone the repository
```bash
git clone <repository-url>
cd helf
```

### 2. Configure environment (optional)
```bash
# Copy example environment file
cp .env.example .env

# Edit .env if needed
nano .env
```

### 3. Build and run with Docker Compose
```bash
docker-compose up -d
```

The application will be available at `http://localhost:30171`

## Configuration

### Environment Variables

Edit `docker-compose.yml` or create a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/app/data` | Directory for TinyDB database and backups |
| `MQTT_BROKER_HOST` | `host.docker.internal` | MQTT broker hostname |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port |
| `CORS_ORIGINS` | `*` | Allowed CORS origins (comma-separated) |
| `PRODUCTION` | `true` | Production mode flag |

### Data Persistence

The application persists data in `/mnt/fast/apps/helf/data` on the host. This includes:
- `helf.json` - TinyDB database
- CSV backups (workouts.csv, body_composition.csv, upcoming_workouts.csv)

To change the data directory, edit the volume mount in `docker-compose.yml`:
```yaml
volumes:
  - /your/custom/path:/app/data
```

### MQTT Integration

For smart scale integration:

1. Ensure your MQTT broker is running on the host
2. Configure the broker connection in `docker-compose.yml`:
   ```yaml
   environment:
     - MQTT_BROKER_HOST=host.docker.internal
     - MQTT_BROKER_PORT=1883
   ```

3. If using a different broker location, update `MQTT_BROKER_HOST`

## Docker Build

The Dockerfile uses a multi-stage build:

1. **frontend-build**: Builds React app with Vite
2. **backend-deps**: Installs Python dependencies with UV
3. **production**: Combines frontend build with FastAPI backend

### Building manually
```bash
docker build -t helf:latest .
```

### Running manually
```bash
docker run -d \
  --name helf-app \
  -p 30171:8080 \
  -v /mnt/fast/apps/helf/data:/app/data \
  -e MQTT_BROKER_HOST=host.docker.internal \
  --add-host host.docker.internal:host-gateway \
  helf:latest
```

## Architecture

```
┌─────────────────────────────────────┐
│   Browser (http://localhost:30171)  │
└──────────────┬──────────────────────┘
               │
               │ HTTP/HTTPS
               ▼
┌─────────────────────────────────────┐
│   FastAPI Server (Port 8080)        │
│   ┌─────────────────────────────┐   │
│   │  React SPA (/)              │   │
│   │  - PWA with offline support │   │
│   │  - Install prompt           │   │
│   └─────────────────────────────┘   │
│   ┌─────────────────────────────┐   │
│   │  REST API (/api/*)          │   │
│   │  - Workouts                 │   │
│   │  - Exercises                │   │
│   │  - Progression              │   │
│   │  - Body Composition         │   │
│   │  - Upcoming Workouts        │   │
│   └─────────────────────────────┘   │
└──────────────┬──────────────────────┘
               │
               │ TinyDB
               ▼
        ┌──────────────┐      ┌──────────┐
        │  helf.json   │      │   MQTT   │
        └──────────────┘      │  Broker  │
                              └──────────┘
```

## Health Checks

The container includes a health check that pings the `/api/health` endpoint every 60 seconds.

View health status:
```bash
docker ps
docker inspect helf-app | grep -A 10 Health
```

## Logs

View application logs:
```bash
docker-compose logs -f
```

View specific component logs:
```bash
docker logs -f helf-app
```

## Updating

### Update to latest version
```bash
cd helf
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### View changes
```bash
docker-compose logs -f
```

## Troubleshooting

### Frontend not loading
- Check that static files were built: `docker exec helf-app ls /app/static`
- Verify API endpoint: `curl http://localhost:30171/api/health`

### MQTT not connecting
- Verify broker is running: `mosquitto -v` or `docker ps | grep mosquitto`
- Check broker host configuration
- View MQTT status: `curl http://localhost:30171/api/mqtt/status`

### Database errors
- Check data directory permissions
- Verify database file exists: `ls -la /mnt/fast/apps/helf/data/helf.json`
- Check container logs: `docker logs helf-app`

### Port already in use
- Change port in `docker-compose.yml`:
  ```yaml
  ports:
    - "8080:8080"  # Use 8080 instead of 30171
  ```

## Development vs Production

### Development Setup

For development with hot reload:

**Backend**:
```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

**Frontend**:
```bash
cd frontend
npm run dev  # Runs on http://localhost:5173
```

### Production Build

Production uses the Docker container with:
- Optimized frontend build (minified, tree-shaken)
- Multi-worker Uvicorn server (4 workers)
- Service worker for offline support
- Static file caching

## Security

### Recommendations for Production

1. **CORS**: Restrict origins in production
   ```yaml
   environment:
     - CORS_ORIGINS=https://yourdomain.com
   ```

2. **HTTPS**: Use a reverse proxy (nginx, Traefik, Caddy) with SSL
3. **Firewall**: Limit port access
4. **Updates**: Keep Docker images updated

## API Documentation

Once running, API docs are available at:
- Swagger UI: `http://localhost:30171/docs`
- ReDoc: `http://localhost:30171/redoc`

## PWA Features

The app is a Progressive Web App with:
- **Offline Support**: Works without internet connection
- **Installable**: Can be installed on mobile/desktop
- **App-like**: Runs in standalone mode

To install:
1. Open the app in a browser
2. Click the install prompt (or browser's install button)
3. App will be added to home screen/app drawer

## Backup and Restore

### Backup
```bash
# Backup database and CSV files
cp -r /mnt/fast/apps/helf/data ~/helf-backup-$(date +%Y%m%d)
```

### Restore
```bash
# Stop container
docker-compose down

# Restore files
cp -r ~/helf-backup-20250101/* /mnt/fast/apps/helf/data/

# Start container
docker-compose up -d
```

## Support

For issues or questions:
- Check logs: `docker-compose logs -f`
- Review API docs: `http://localhost:30171/docs`
- Check health: `http://localhost:30171/api/health`

---

**Version**: 2.0.0  
**Last Updated**: December 25, 2025
