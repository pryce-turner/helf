"""Body composition data models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class BodyCompositionBase(BaseModel):
    """Base body composition model."""
    timestamp: datetime
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    weight: float
    weight_unit: str = "kg"
    body_fat_pct: Optional[float] = Field(None, ge=0, le=100)
    muscle_mass: Optional[float] = None
    bmi: Optional[float] = None
    water_pct: Optional[float] = Field(None, ge=0, le=100)
    bone_mass: Optional[float] = None
    visceral_fat: Optional[float] = None
    metabolic_age: Optional[int] = None
    protein_pct: Optional[float] = Field(None, ge=0, le=100)


class BodyCompositionCreate(BodyCompositionBase):
    """Model for creating a body composition measurement."""
    pass


class BodyComposition(BodyCompositionBase):
    """Full body composition model with metadata."""
    id: int = Field(..., alias="doc_id")
    created_at: datetime

    class Config:
        populate_by_name = True
        from_attributes = True


class BodyCompositionStats(BaseModel):
    """Body composition summary statistics."""
    total_measurements: int
    latest_weight: Optional[float] = None
    latest_body_fat: Optional[float] = None
    latest_muscle_mass: Optional[float] = None
    weight_change: Optional[float] = None
    body_fat_change: Optional[float] = None
    muscle_mass_change: Optional[float] = None
    first_date: Optional[str] = None
    latest_date: Optional[str] = None


class BodyCompositionTrend(BaseModel):
    """Trend data for charts."""
    dates: list[str]
    weights: list[float | None]
    body_fat_pcts: list[float | None]
    muscle_masses: list[float | None]
    water_pcts: list[float | None]
