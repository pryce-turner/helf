"""Progression data models."""


from pydantic import BaseModel


class ProgressionDataPoint(BaseModel):
    """Single progression data point."""
    date: str
    weight: float
    weight_unit: str
    reps: int
    estimated_1rm: float
    comment: str | None = None


class UpcomingProgressionDataPoint(BaseModel):
    """Single upcoming progression data point."""
    session: int
    projected_date: str
    weight: float
    weight_unit: str
    reps: int
    estimated_1rm: float
    comment: str | None = None


class ProgressionResponse(BaseModel):
    """Progression data for an exercise."""
    exercise: str
    historical: list[ProgressionDataPoint]
    upcoming: list[UpcomingProgressionDataPoint]
