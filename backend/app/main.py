"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import close_db
from app.api import workouts, exercises, progression, upcoming, body_comp
from app.services.mqtt_service import MQTTService

# Global MQTT service instance
mqtt_service: MQTTService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown."""
    global mqtt_service

    # Startup
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


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "message": "Helf API",
        "version": settings.app_version,
        "docs": "/docs",
    }
