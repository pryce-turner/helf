"""Body composition data models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BodyCompositionBase(BaseModel):
    """Base body composition model."""
    timestamp: datetime
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    weight: float
    weight_unit: str = "lbs"
    body_fat_pct: float | None = Field(None, ge=0, le=100)
    muscle_mass: float | None = None
    bmi: float | None = None
    water_pct: float | None = Field(None, ge=0, le=100)
    # kg, unlike its neighbours, and the name says so. `metric_def` defines
    # bone as kg for DEXA (Plan 0008) and openScale reports kg; a second name
    # in pounds would put one quantity under two names, which is what
    # ADR-0003's naming rule exists to prevent.
    bone_mass_kg: float | None = None
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
    # Which instrument produced this. A bioimpedance estimate and a DEXA
    # measurement of the same quantity are not interchangeable, and a consumer
    # that cannot tell them apart will eventually average them.
    source: str = "openscale"

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class BodyCompositionStats(BaseModel):
    """Body composition summary statistics.

    The `latest_*` figures are the most recent values recorded, whatever
    produced them. The `*_change` figures are deltas *within a single source* -
    subtracting a DEXA body fat from a bioimpedance one measures the gap
    between two instruments, not a change in the body. `primary_source` names
    the series the deltas describe.
    """
    total_measurements: int
    latest_weight: float | None = None
    latest_body_fat: float | None = None
    latest_muscle_mass: float | None = None
    latest_source: str | None = None
    weight_change: float | None = None
    body_fat_change: float | None = None
    muscle_mass_change: float | None = None
    primary_source: str | None = None
    first_date: str | None = None
    latest_date: str | None = None


class BodyCompositionSyncResult(BaseModel):
    """What one BodySpec sync did.

    `skipped` is the number of scans already held. On a second run it should
    equal `scans_found` with `imported` at zero - idempotency is the property
    most likely to break here, and the failure mode is silent duplicate
    history.
    """
    scans_found: int
    imported: int
    skipped: int
    metrics_written: int


class BodyCompositionTrend(BaseModel):
    """Trend data for charts.

    `sources` runs parallel to `dates`, so a chart can split the points by
    instrument. Without it a client joins a quarterly DEXA point to a daily
    scale reading with a straight line, asserting a trajectory across three
    months that nothing measured.
    """
    dates: list[str]
    weights: list[float | None]
    body_fat_pcts: list[float | None]
    muscle_masses: list[float | None]
    water_pcts: list[float | None]
    sources: list[str] = []
