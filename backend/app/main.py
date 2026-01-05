"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import settings
from app.database import close_db, init_db
from app.api import workouts, exercises, progression, upcoming, body_comp
from app.services.mqtt_service import MQTTService

# Global MQTT service instance
mqtt_service: MQTTService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown."""
    global mqtt_service

    # Startup
    init_db()
    mqtt_service = MQTTService(
        broker_host=settings.mqtt_broker_host,
        broker_port=settings.mqtt_broker_port,
    )
    mqtt_service.start()

    yield

    # Shutdown
    if mqtt_service:
        mqtt_service.stop()
    close_db()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(workouts.router, prefix="/api/workouts", tags=["workouts"])
app.include_router(exercises.router, prefix="/api/exercises", tags=["exercises"])
app.include_router(progression.router, prefix="/api/progression", tags=["progression"])
app.include_router(upcoming.router, prefix="/api/upcoming", tags=["upcoming"])
app.include_router(body_comp.router, prefix="/api/body-composition", tags=["body-composition"])


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.app_version,
    }


@app.get("/api/mqtt/status")
def mqtt_status():
    """Get MQTT connection status."""
    if mqtt_service:
        return mqtt_service.get_status()
    return {"connected": False, "broker": "not initialized"}


@app.post("/api/mqtt/reconnect")
def mqtt_reconnect():
    """Trigger MQTT reconnection."""
    global mqtt_service

    if mqtt_service:
        mqtt_service.stop()
        mqtt_service.start()
        return {"message": "MQTT reconnection triggered"}

    return {"message": "MQTT service not initialized"}


# Serve static files (React app) if they exist
# In development, look for frontend build in ../frontend/dist
# In production (Docker), look in /app/static
static_dir = Path("/app/static")
if not static_dir.exists():
    static_dir = Path(__file__).parent.parent.parent / "frontend" / "dist"

if static_dir.exists() and static_dir.is_dir():
    # Mount static files for assets
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    # Serve static files (manifest, service worker, icons)
    @app.get("/manifest.webmanifest")
    async def manifest():
        return FileResponse(static_dir / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js")
    async def service_worker():
        return FileResponse(static_dir / "sw.js", media_type="application/javascript")

    @app.get("/workbox-{filename:path}")
    async def workbox(filename: str):
        return FileResponse(static_dir / f"workbox-{filename}", media_type="application/javascript")

    @app.get("/{filename}.png")
    async def icons(filename: str):
        file_path = static_dir / f"{filename}.png"
        if file_path.exists():
            return FileResponse(file_path, media_type="image/png")

    # Root route serves index.html
    @app.get("/")
    async def root():
        return FileResponse(static_dir / "index.html", media_type="text/html")

    # SPA routes - specific paths for React Router
    @app.get("/calendar")
    async def spa_calendar():
        return FileResponse(static_dir / "index.html", media_type="text/html")

    @app.get("/day/{date}")
    async def spa_day(date: str):
        return FileResponse(static_dir / "index.html", media_type="text/html")

    @app.get("/progression")
    async def spa_progression():
        return FileResponse(static_dir / "index.html", media_type="text/html")

    @app.get("/progression/{exercise}")
    async def spa_progression_exercise(exercise: str):
        return FileResponse(static_dir / "index.html", media_type="text/html")

    @app.get("/upcoming")
    async def spa_upcoming():
        return FileResponse(static_dir / "index.html", media_type="text/html")

    @app.get("/body-composition")
    async def spa_body_composition():
        return FileResponse(static_dir / "index.html", media_type="text/html")
else:
    @app.get("/")
    def root():
        """Root endpoint when frontend is not available."""
        return {
            "message": "Helf API",
            "version": settings.app_version,
            "docs": "/docs",
        }
