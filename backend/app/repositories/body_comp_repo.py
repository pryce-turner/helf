"""Body composition repository for database operations."""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.db.models import BodyComposition
from app.models.body_composition import BodyCompositionCreate
from app.utils.date_helpers import PACIFIC_TZ, get_current_datetime


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

    def create(self, measurement: BodyCompositionCreate) -> dict | None:
        """Create a new measurement. Returns None if duplicate timestamp."""
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
                weight_unit=measurement_dict.get("weight_unit") or "kg",
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
            return self._serialize(new_measurement)

    def delete(self, doc_id: int) -> bool:
        """Delete a measurement."""
        with SessionLocal() as session:
            measurement = session.get(BodyComposition, doc_id)
            if not measurement:
                return False
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
