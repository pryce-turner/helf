"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Category(Base):
    """Exercise category."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    exercises: Mapped[list["Exercise"]] = relationship(
        "Exercise", back_populates="category", cascade="all, delete-orphan"
    )
    workouts: Mapped[list["Workout"]] = relationship("Workout", back_populates="category")
    upcoming_workouts: Mapped[list["UpcomingWorkout"]] = relationship(
        "UpcomingWorkout", back_populates="category"
    )


class Exercise(Base):
    """Exercise definition."""

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_used: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    category: Mapped[Category] = relationship("Category", back_populates="exercises")
    workouts: Mapped[list["Workout"]] = relationship("Workout", back_populates="exercise")
    upcoming_workouts: Mapped[list["UpcomingWorkout"]] = relationship(
        "UpcomingWorkout", back_populates="exercise"
    )


class Workout(Base):
    """Historical workout entry."""

    __tablename__ = "workouts"
    __table_args__ = (Index("ix_workouts_date_order", "date", "order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False, index=True
    )
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    exercise: Mapped[Exercise] = relationship("Exercise", back_populates="workouts")
    category: Mapped[Category] = relationship("Category", back_populates="workouts")


class UpcomingWorkout(Base):
    """Planned upcoming workout entry."""

    __tablename__ = "upcoming_workouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False, index=True
    )
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    exercise: Mapped[Exercise] = relationship("Exercise", back_populates="upcoming_workouts")
    category: Mapped[Category] = relationship("Category", back_populates="upcoming_workouts")


class MetricDef(Base):
    """Vocabulary of measurable quantities.

    A definition, not storage. Declaring a metric here costs nothing and fixes
    its name and unit before anything writes it, which is the cheapest moment to
    get those right. A definition with no rows behind it is reported honestly by
    the `v_metric_coverage` view (n_rows = 0) rather than looking like a series
    that happens to be flat.
    """

    __tablename__ = "metric_def"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_high: Mapped[float | None] = mapped_column(Float, nullable=True)

    metrics: Mapped[list["Metric"]] = relationship("Metric", back_populates="definition")


class Metric(Base):
    """A single observed value: tall storage for anything measurable.

    Replaces the wide `body_composition` table, five of whose nine columns have
    never held a value. Adding a quantity here is a row, not a migration.
    """

    __tablename__ = "metric"
    __table_args__ = (
        # reference/qs_mcp.py upserts ON CONFLICT(observed_at, name, source), so
        # this triple must be unique or the agent's write tool raises at runtime.
        # It also keeps a bioimpedance estimate and a DEXA measurement of the
        # same quantity on the same day as two rows rather than one overwriting
        # the other.
        UniqueConstraint("observed_at", "name", "source", name="uq_metric_observation"),
        CheckConstraint(
            "value IS NOT NULL OR text_value IS NOT NULL",
            name="ck_metric_has_a_value",
        ),
        Index("ix_metric_date_name", "date", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observed_at: Mapped[str] = mapped_column(String(32), nullable=False)
    # STORED rather than VIRTUAL so it can be indexed. This is the universal
    # join key across every quantity the system records.
    date: Mapped[str] = mapped_column(
        String(10),
        Computed("substr(observed_at, 1, 10)", persisted=True),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        ForeignKey("metric_def.name"), nullable=False
    )
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")

    definition: Mapped[MetricDef] = relationship("MetricDef", back_populates="metrics")


class BodyComposition(Base):
    """Body composition measurement.

    Legacy wide table. Superseded by `metric` but kept and dual-written until the
    view-backed path is verified against real numbers; dropping it is a later
    plan (docs/plans/0003-units-and-metrics.md §4).
    """

    __tablename__ = "body_composition"
    __table_args__ = (Index("ix_body_composition_date_timestamp", "date", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True, nullable=False)
    date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    weight_unit: Mapped[str] = mapped_column(String(8), nullable=False)
    body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    muscle_mass: Mapped[float | None] = mapped_column(Float, nullable=True)
    bmi: Mapped[float | None] = mapped_column(Float, nullable=True)
    water_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    bone_mass: Mapped[float | None] = mapped_column(Float, nullable=True)
    visceral_fat: Mapped[float | None] = mapped_column(Float, nullable=True)
    metabolic_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protein_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
