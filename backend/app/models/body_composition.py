"""Body composition data models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BodyCompositionBase(BaseModel):
    """Base body composition model."""
    timestamp: datetime
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    weight: float
    weight_unit: str = "kg"
    body_fat_pct: float | None = Field(None, ge=0, le=100)
    muscle_mass: float | None = None
    bmi: float | None = None
    water_pct: float | None = Field(None, ge=0, le=100)
    bone_mass: float | None = None
    visceral_fat: float | None = None
    metabolic_age: int | None = None
    protein_pct: float | None = Field(None, ge=0, le=100)


class BodyCompositionCreate(BodyCompositionBase):
    """Model for creating a body composition measurement."""
    pass


class BodyComposition(BodyCompositionBase):
    """Full body composition model with metadata."""
    id: int = Field(..., alias="doc_id")
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class BodyCompositionStats(BaseModel):
    """Body composition summary statistics."""
    total_measurements: int
    latest_weight: float | None = None
    latest_body_fat: float | None = None
    latest_muscle_mass: float | None = None
    weight_change: float | None = None
    body_fat_change: float | None = None
    muscle_mass_change: float | None = None
    first_date: str | None = None
    latest_date: str | None = None


class BodyCompositionTrend(BaseModel):
    """Trend data for charts."""
    dates: list[str]
    weights: list[float | None]
    body_fat_pcts: list[float | None]
    muscle_masses: list[float | None]
    water_pcts: list[float | None]
