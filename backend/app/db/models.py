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
    text,
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
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    exercise: Mapped[Exercise] = relationship("Exercise", back_populates="upcoming_workouts")
    category: Mapped[Category] = relationship("Category", back_populates="upcoming_workouts")


class Document(Base):
    """A raw imported payload, kept whole.

    Promotion into `metric` is deliberately lossy - a BodySpec DEXA scan
    flattens to well over a hundred scalars and thirteen are worth charting
    (docs/plans/0008-bodyspec-integration.md §5). The rest live here, reachable
    with `json_extract`, so promoting one later is a re-run over stored
    documents rather than a re-fetch from an API.

    `external_id` is the upstream identity - BodySpec's `result_id` - and the
    unique index over (kind, external_id) is what makes a re-poll a no-op
    instead of duplicate history.
    """

    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint("json_valid(raw)", name="ck_document_raw_is_json"),
        # NULLs are distinct in a SQLite UNIQUE index, so documents with no
        # upstream identity coexist freely while a `result_id` appears at most
        # once per kind.
        Index("ux_document_kind_external", "kind", "external_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    imported_at: Mapped[str] = mapped_column(
        Text, server_default=text("(datetime('now'))"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[str] = mapped_column(Text, nullable=False)

    metrics: Mapped[list["Metric"]] = relationship("Metric", back_populates="document")


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


class Observation(Base):
    """One act of measuring: a time, an instrument, and the values it produced.

    The tall model needs this because a "measurement" is several `metric` rows -
    a scale reports weight, body fat, muscle and water in one step off. Without
    an observation to hang them on there is nothing to give a stable id to, no
    home for ingestion time, and no way for `DELETE /{id}` to name what to
    remove.
    """

    __tablename__ = "observation"
    __table_args__ = (
        # An instrument produces at most one reading per instant. This is what
        # keeps a bioimpedance estimate and a DEXA scan on the same day as two
        # observations rather than one overwriting the other.
        UniqueConstraint("observed_at", "source", name="uq_observation_instant"),
        Index("ix_observation_date", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observed_at: Mapped[str] = mapped_column(String(32), nullable=False)
    # STORED rather than VIRTUAL so it can be indexed. The universal join key
    # across every quantity the system records.
    date: Mapped[str] = mapped_column(
        String(10),
        Computed("substr(observed_at, 1, 10)", persisted=True),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    metrics: Mapped[list["Metric"]] = relationship(
        "Metric", back_populates="observation", cascade="all, delete-orphan"
    )


class Metric(Base):
    """A single named value belonging to an observation.

    Replaces the wide `body_composition` table, five of whose nine columns have
    never held a value. Adding a quantity here is a row, not a migration.
    """

    __tablename__ = "metric"
    __table_args__ = (
        # One value per name per observation. Equivalent to the old
        # UNIQUE(observed_at, name, source), since `observation` is itself
        # unique on (observed_at, source).
        UniqueConstraint("observation_id", "name", name="uq_metric_observation"),
        CheckConstraint(
            "value IS NOT NULL OR text_value IS NOT NULL",
            name="ck_metric_has_a_value",
        ),
        Index("ix_metric_name", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(
        ForeignKey("observation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(
        ForeignKey("metric_def.name"), nullable=False
    )
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Provenance: the payload this value was promoted from, where there was
    # one. NULL for anything entered by hand or read off an MQTT topic.
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("document.id"), nullable=True
    )

    observation: Mapped[Observation] = relationship(
        "Observation", back_populates="metrics"
    )
    definition: Mapped[MetricDef] = relationship("MetricDef", back_populates="metrics")
    document: Mapped["Document | None"] = relationship(
        "Document", back_populates="metrics"
    )


class Food(Base):
    """A food and the macros in one serving of it.

    Macros live here, not on `FoodLog`: a serving's numbers are derived
    (`servings x kcal_per_serving`), so correcting a food's macros
    retroactively corrects every past log entry. The cost is that editing a
    food rewrites history silently, which is what Plan 0007's audit log is for.

    `brand` is `''` rather than NULL for brandless foods. SQLite treats NULLs
    as distinct in a UNIQUE index, so a nullable column would make
    `UNIQUE (name, brand)` decorative.
    """

    __tablename__ = "food"
    __table_args__ = (UniqueConstraint("name", "brand", name="uq_food_name_brand"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    serving_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    kcal_per_serving: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carb_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[str] = mapped_column(
        Text, server_default=text("(datetime('now'))"), nullable=False
    )

    logs: Mapped[list["FoodLog"]] = relationship("FoodLog", back_populates="food")


class FoodLog(Base):
    """One consumption event: a food, an amount, and when."""

    __tablename__ = "food_log"
    __table_args__ = (
        CheckConstraint(
            "meal IN ('breakfast','lunch','dinner','snack') OR meal IS NULL",
            name="ck_food_log_meal",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consumed_at: Mapped[str] = mapped_column(Text, nullable=False)
    # STORED, so it can be indexed and joined against `observation.date`,
    # `workouts.date` and `note.date`. `Computed` is what stops SQLAlchemy
    # trying to INSERT into it, which SQLite refuses outright.
    date: Mapped[str] = mapped_column(
        Text,
        Computed("substr(consumed_at, 1, 10)", persisted=True),
        nullable=False,
        index=True,
    )
    food_id: Mapped[int] = mapped_column(
        ForeignKey("food.id"), nullable=False, index=True
    )
    servings: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    meal: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        Text, server_default=text("(datetime('now'))"), nullable=False
    )

    food: Mapped[Food] = relationship("Food", back_populates="logs")


class Note(Base):
    """Prose with a date on it: the landing zone for anything unshaped.

    Together with `Document` this is the journal (Plan 0005 §1a) - staging,
    expected to be superseded, explicitly *not* the audit log. A named scalar
    over time does not belong here; that already has a shape and goes in
    `metric` with a `metric_def` entry.

    `kind` is unconstrained on purpose. `source` distinguishes what was
    observed from what a model inferred, which becomes unanswerable once the
    agent can write notes.
    """

    __tablename__ = "note"
    __table_args__ = (Index("ix_note_date_kind", "date", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    noted_at: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[str] = mapped_column(
        Text,
        Computed("substr(noted_at, 1, 10)", persisted=True),
        nullable=False,
    )
    kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")


class AuditActor(Base):
    """Who the database should attribute the next write to. Exactly one row.

    Plan 0007 §3 wanted a per-connection `TEMP` marker. SQLite forbids it
    outright - *"trigger cannot reference objects in database temp"* - and an
    unqualified name binds to `main` when the trigger is compiled, so a
    connection's temp shadow is never seen. The marker therefore has to be a
    real table.

    That is safe only because SQLite has **one writer at a time**: an actor set
    inside a write transaction cannot have another writer's rows attributed to
    it, provided the writer takes the write lock up front. A writer that never
    touches this row is `'app'`, which is the PWA, and stays correct because
    the only other writer has to opt in explicitly.
    """

    __tablename__ = "audit_actor"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_audit_actor_single_row"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False, server_default="app")


class AuditLog(Base):
    """What changed, when, and who changed it.

    Append-only, enforced by `BEFORE UPDATE`/`BEFORE DELETE` triggers that
    `RAISE(ABORT)`. Populated by triggers too, not by this application: there
    are two writers (ADR-0002) and application-level auditing would cover one
    of them.

    Emphatically **not** the journal. `note` and `document` hold observations
    awaiting a shape and exist to be restructured; this holds mutations and
    exists to be unchangeable. Staging data in an append-only table can never
    be corrected.

    No relationships and no repository writes - it is written by the database
    and read by the agent over the read-only connection.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("op IN ('INSERT','UPDATE','DELETE')", name="ck_audit_log_op"),
        CheckConstraint(
            "old_values IS NULL OR json_valid(old_values)",
            name="ck_audit_log_old_is_json",
        ),
        CheckConstraint(
            "new_values IS NULL OR json_valid(new_values)",
            name="ck_audit_log_new_is_json",
        ),
        Index("ix_audit_log_table_row", "table_name", "row_id"),
        Index("ix_audit_log_changed_at", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    changed_at: Mapped[str] = mapped_column(
        Text, server_default=text("(datetime('now'))"), nullable=False
    )
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    op: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False, server_default="app")
    old_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_values: Mapped[str | None] = mapped_column(Text, nullable=True)


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
    body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    muscle_mass: Mapped[float | None] = mapped_column(Float, nullable=True)
    bmi: Mapped[float | None] = mapped_column(Float, nullable=True)
    water_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    bone_mass: Mapped[float | None] = mapped_column(Float, nullable=True)
    visceral_fat: Mapped[float | None] = mapped_column(Float, nullable=True)
    metabolic_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protein_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
