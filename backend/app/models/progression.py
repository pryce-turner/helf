"""Progression data models."""

from pydantic import BaseModel
from typing import Optional


class ProgressionDataPoint(BaseModel):
    """Single progression data point."""
    date: str
    weight: float
    weight_unit: str
    reps: int | str
    estimated_1rm: float
    comment: Optional[str] = None


class UpcomingProgressionDataPoint(BaseModel):
    """Single upcoming progression data point."""
    session: int
    projected_date: str
    weight: float
    weight_unit: str
    reps: int | str
    estimated_1rm: float
    comment: Optional[str] = None


class ProgressionResponse(BaseModel):
    """Progression data for an exercise."""
    exercise: str
    historical: list[ProgressionDataPoint]
    upcoming: list[UpcomingProgressionDataPoint]
