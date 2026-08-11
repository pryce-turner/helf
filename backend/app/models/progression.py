"""Progression data models."""


from pydantic import BaseModel


class ProgressionSet(BaseModel):
    """One logged set within a day."""
    weight: float
    weight_unit: str
    reps: int
    estimated_1rm: float
    comment: str | None = None


class ProgressionDataPoint(BaseModel):
    """A day's work on one exercise.

    The top-level numbers are the day's *best* set by estimated 1RM, which is
    what the chart plots — one point per session, because plotting every set
    turns a progression line into a cloud. `sets` carries the whole day
    underneath it, so the history list can show the session as it happened:
    three sets across at 160, not just the heaviest of them.
    """
    date: str
    weight: float
    weight_unit: str
    reps: int
    estimated_1rm: float
    comment: str | None = None
    sets: list[ProgressionSet] = []


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
