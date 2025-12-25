"""Body composition API endpoints."""

from fastapi import APIRouter, HTTPException, Query as QueryParam
from typing import Optional

from app.models.body_composition import (
    BodyComposition,
    BodyCompositionCreate,
    BodyCompositionStats,
    BodyCompositionTrend,
)
from app.repositories.body_comp_repo import BodyCompositionRepository

router = APIRouter()


@router.get("/", response_model=list[BodyComposition])
def get_measurements(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
):
    """Get body composition measurements."""
    repo = BodyCompositionRepository()

    if start_date and end_date:
        return repo.get_by_date_range(start_date, end_date)

    return repo.get_all(skip=skip, limit=limit)


@router.get("/latest", response_model=Optional[BodyComposition])
def get_latest_measurement():
    """Get the most recent measurement."""
    repo = BodyCompositionRepository()
    latest = repo.get_latest()

    if not latest:
        raise HTTPException(status_code=404, detail="No measurements found")

    return latest


@router.get("/stats", response_model=BodyCompositionStats)
def get_stats():
    """Get summary statistics."""
    repo = BodyCompositionRepository()
    return repo.get_stats()


@router.get("/trends", response_model=BodyCompositionTrend)
def get_trends(
    days: int = QueryParam(30, ge=1, le=365, description="Number of days"),
):
    """Get trend data for charts."""
    repo = BodyCompositionRepository()
    measurements = repo.get_recent(days=days)

    dates = []
    weights = []
    body_fat_pcts = []
    muscle_masses = []
    water_pcts = []

    for m in measurements:
        dates.append(m.get('date', ''))
        weights.append(m.get('weight'))
        body_fat_pcts.append(m.get('body_fat_pct'))
        muscle_masses.append(m.get('muscle_mass'))
        water_pcts.append(m.get('water_pct'))

    return BodyCompositionTrend(
        dates=dates,
        weights=weights,
        body_fat_pcts=body_fat_pcts,
        muscle_masses=muscle_masses,
        water_pcts=water_pcts,
    )


@router.post("/", response_model=BodyComposition, status_code=201)
def create_measurement(measurement: BodyCompositionCreate):
    """Create a new measurement (manual entry)."""
    repo = BodyCompositionRepository()
    created = repo.create(measurement)

    if not created:
        raise HTTPException(
            status_code=409,
            detail="Measurement with this timestamp already exists"
        )

    return created


@router.delete("/{measurement_id}", status_code=204)
def delete_measurement(measurement_id: int):
    """Delete a measurement."""
    repo = BodyCompositionRepository()
    deleted = repo.delete(measurement_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Measurement not found")
