"""Body composition repository for database operations."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.database import SessionLocal
from app.db.models import BodyComposition, Metric
from app.models.body_composition import BodyCompositionCreate
from app.utils.date_helpers import PACIFIC_TZ, get_current_datetime

logger = logging.getLogger(__name__)

# Wide column -> (metric name, unit). Mirrors the a3 backfill exactly; the two
# must agree or history and new readings end up under different names.
#
# `muscle_mass` holds a percentage despite its name, so it maps to `muscle_pct`.
METRIC_COLUMNS = [
    ("weight", "body_weight_lb", "lb"),
    ("body_fat_pct", "body_fat_pct", "%"),
    ("muscle_mass", "muscle_pct", "%"),
    ("water_pct", "water_pct", "%"),
]


def _observed_at(timestamp: datetime) -> str:
    """Render a timestamp the way SQLAlchemy's SQLite DATETIME does.

    `metric.observed_at` is TEXT and the backfill copied `body_composition.
    timestamp` verbatim, so new rows must use byte-identical formatting or they
    will not line up with history - and the UNIQUE(observed_at, name, source)
    constraint would stop deduplicating.
    """
    return timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")


class BodyCompositionRepository:
    """Repository for body composition data operations."""

    def _serialize(self, measurement: BodyComposition) -> dict:
        return {
            "doc_id": measurement.id,
            "timestamp": measurement.timestamp,
            "date": measurement.date,
            "weight": measurement.weight,
            "weight_unit": measurement.weight_unit,
            "body_fat_pct": measurement.body_fat_pct,
            "muscle_mass": measurement.muscle_mass,
            "bmi": measurement.bmi,
            "water_pct": measurement.water_pct,
            "bone_mass": measurement.bone_mass,
            "visceral_fat": measurement.visceral_fat,
            "metabolic_age": measurement.metabolic_age,
            "protein_pct": measurement.protein_pct,
            "created_at": measurement.created_at,
        }

    def get_all(self, skip: int = 0, limit: int = 100) -> list[dict]:
        """Get all measurements with pagination."""
        with SessionLocal() as session:
            measurements = session.execute(
                select(BodyComposition)
                .order_by(BodyComposition.timestamp.desc())
                .offset(skip)
                .limit(limit)
            ).scalars().all()
            return [self._serialize(m) for m in measurements]

    def get_by_id(self, doc_id: int) -> dict | None:
        """Get a measurement by ID."""
        with SessionLocal() as session:
            measurement = session.get(BodyComposition, doc_id)
            return self._serialize(measurement) if measurement else None

    def get_latest(self) -> dict | None:
        """Get the most recent measurement."""
        with SessionLocal() as session:
            measurement = session.execute(
                select(BodyComposition).order_by(BodyComposition.timestamp.desc()).limit(1)
            ).scalar_one_or_none()
            return self._serialize(measurement) if measurement else None

    def get_by_date_range(self, start_date: str, end_date: str) -> list[dict]:
        """Get measurements within a date range."""
        with SessionLocal() as session:
            measurements = session.execute(
                select(BodyComposition)
                .where(BodyComposition.date >= start_date)
                .where(BodyComposition.date <= end_date)
                .order_by(BodyComposition.timestamp.asc())
            ).scalars().all()
            return [self._serialize(m) for m in measurements]

    def get_recent(self, days: int = 30) -> list[dict]:
        """Get measurements from the last N days."""
        cutoff_date = (
            datetime.now(PACIFIC_TZ).date() - timedelta(days=days)
        ).isoformat()

        with SessionLocal() as session:
            measurements = session.execute(
                select(BodyComposition)
                .where(BodyComposition.date >= cutoff_date)
                .order_by(BodyComposition.timestamp.asc())
            ).scalars().all()
            return [self._serialize(m) for m in measurements]

    def create(
        self, measurement: BodyCompositionCreate, source: str = "manual"
    ) -> dict | None:
        """Create a new measurement. Returns None if duplicate timestamp.

        `source` tags the mirrored `metric` rows so instruments of different
        accuracy stay distinguishable - a bioimpedance reading and a DEXA scan
        of the same quantity must never be averaged together. Defaults to
        "manual"; the MQTT ingest path passes "openscale", matching the
        backfilled history.
        """
        timestamp = measurement.timestamp

        with SessionLocal() as session:
            existing = session.execute(
                select(BodyComposition).where(BodyComposition.timestamp == timestamp)
            ).scalar_one_or_none()
            if existing:
                return None

            now = get_current_datetime()
            measurement_dict = measurement.model_dump(exclude_none=False)

            new_measurement = BodyComposition(
                timestamp=timestamp,
                date=measurement_dict["date"],
                weight=measurement_dict["weight"],
                weight_unit=measurement_dict.get("weight_unit") or "lbs",
                body_fat_pct=measurement_dict.get("body_fat_pct"),
                muscle_mass=measurement_dict.get("muscle_mass"),
                bmi=measurement_dict.get("bmi"),
                water_pct=measurement_dict.get("water_pct"),
                bone_mass=measurement_dict.get("bone_mass"),
                visceral_fat=measurement_dict.get("visceral_fat"),
                metabolic_age=measurement_dict.get("metabolic_age"),
                protein_pct=measurement_dict.get("protein_pct"),
                created_at=now,
            )
            session.add(new_measurement)
            session.commit()
            session.refresh(new_measurement)
            serialized = self._serialize(new_measurement)

        # Deliberately AFTER the commit above and in its own transaction.
        #
        # `body_composition` is still the source of truth, and a scale reading
        # that fails to store is gone for good - openScale does not retransmit.
        # A divergence between the two tables is recoverable (re-run the
        # backfill); a lost measurement is not. So the mirror is never allowed
        # to roll back the primary write.
        self._mirror_to_metric(new_measurement, source)
        return serialized

    def _mirror_to_metric(self, measurement: BodyComposition, source: str) -> None:
        """Write the same reading into the tall `metric` table.

        Dual-write window: both tables are maintained until the read path moves
        onto the views (docs/plans/0003-units-and-metrics.md §4).
        """
        observed_at = _observed_at(measurement.timestamp)
        try:
            with SessionLocal() as session:
                for column, metric_name, unit in METRIC_COLUMNS:
                    value = getattr(measurement, column)
                    if value is None:
                        continue
                    session.add(
                        Metric(
                            observed_at=observed_at,
                            name=metric_name,
                            value=value,
                            unit=unit,
                            source=source,
                        )
                    )
                session.commit()
        except Exception:
            # Loud, but not fatal: the measurement itself is already safe.
            logger.exception(
                "Failed to mirror measurement %s into `metric`; "
                "body_composition is authoritative and can be re-backfilled",
                observed_at,
            )

    def delete(self, doc_id: int) -> bool:
        """Delete a measurement and its mirrored metric rows."""
        with SessionLocal() as session:
            measurement = session.get(BodyComposition, doc_id)
            if not measurement:
                return False

            # One transaction here: unlike create, a failure loses nothing.
            session.execute(
                sa_delete(Metric).where(
                    Metric.observed_at == _observed_at(measurement.timestamp),
                    Metric.name.in_([name for _c, name, _u in METRIC_COLUMNS]),
                )
            )
            session.delete(measurement)
            session.commit()
            return True

    def get_stats(self) -> dict:
        """Get summary statistics.

        Every ``*_change`` is the same comparison: the earliest recorded value
        for that metric against the most recent, across all history.

        `weight_change` used to be a rolling 30-day vs previous-30-day average
        delta while the other two were first-vs-latest, so three figures
        displayed side by side on one row meant two different things. It also
        read `None` whenever the most recent measurement was over 30 days old,
        which is a common state for a scale that isn't used daily.
        """
        with SessionLocal() as session:
            measurements = session.execute(
                select(BodyComposition).order_by(BodyComposition.timestamp.asc())
            ).scalars().all()
            if not measurements:
                return {
                    "total_measurements": 0,
                    "latest_weight": None,
                    "latest_body_fat": None,
                    "latest_muscle_mass": None,
                    "weight_change": None,
                    "body_fat_change": None,
                    "muscle_mass_change": None,
                    "first_date": None,
                    "latest_date": None,
                }

            first = measurements[0]
            latest = measurements[-1]

            def safe_float(value):
                try:
                    return float(value) if value is not None else None
                except (ValueError, TypeError):
                    return None

            def change(attr: str) -> float | None:
                """Earliest-to-latest delta for one metric.

                Scoped per metric rather than to the first and last rows
                overall: a single missing value in the earliest row would
                otherwise suppress a change that months of data support. That
                matters increasingly as sources with different column coverage
                are added - BodySpec populates fields openScale never does.

                Returns None below two data points, where a change is undefined
                rather than zero.
                """
                values = [
                    v
                    for v in (safe_float(getattr(m, attr)) for m in measurements)
                    if v is not None
                ]
                if len(values) < 2:
                    return None
                return values[-1] - values[0]

            return {
                "total_measurements": len(measurements),
                "latest_weight": safe_float(latest.weight),
                "latest_body_fat": safe_float(latest.body_fat_pct),
                "latest_muscle_mass": safe_float(latest.muscle_mass),
                "weight_change": change("weight"),
                "body_fat_change": change("body_fat_pct"),
                "muscle_mass_change": change("muscle_mass"),
                "first_date": first.date,
                "latest_date": latest.date,
            }
