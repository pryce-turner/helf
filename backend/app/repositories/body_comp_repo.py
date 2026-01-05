"""Body composition repository for database operations."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from app.database import SessionLocal
from app.db.models import BodyComposition
from app.models.body_composition import BodyCompositionCreate
from app.utils.date_helpers import get_current_datetime, PACIFIC_TZ


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

    def get_by_id(self, doc_id: int) -> Optional[dict]:
        """Get a measurement by ID."""
        with SessionLocal() as session:
            measurement = session.get(BodyComposition, doc_id)
            return self._serialize(measurement) if measurement else None

    def get_latest(self) -> Optional[dict]:
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

    def create(self, measurement: BodyCompositionCreate) -> Optional[dict]:
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
        """Get summary statistics."""
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

            now = datetime.now(PACIFIC_TZ)
            thirty_days_ago = now - timedelta(days=30)
            sixty_days_ago = now - timedelta(days=60)

            last_30_days = [m for m in measurements if m.timestamp >= thirty_days_ago]
            prev_30_days = [
                m for m in measurements if sixty_days_ago <= m.timestamp < thirty_days_ago
            ]

            def calculate_avg_weight(measurement_list):
                weights = [m.weight for m in measurement_list if m.weight is not None]
                return sum(weights) / len(weights) if weights else None

            avg_weight_last_30 = calculate_avg_weight(last_30_days)
            avg_weight_prev_30 = calculate_avg_weight(prev_30_days)

            weight_change = None
            if avg_weight_last_30 is not None and avg_weight_prev_30 is not None:
                weight_change = avg_weight_last_30 - avg_weight_prev_30

            def safe_float(value):
                try:
                    return float(value) if value is not None else None
                except (ValueError, TypeError):
                    return None

            return {
                "total_measurements": len(measurements),
                "latest_weight": safe_float(latest.weight),
                "latest_body_fat": safe_float(latest.body_fat_pct),
                "latest_muscle_mass": safe_float(latest.muscle_mass),
                "weight_change": weight_change,
                "body_fat_change": (
                    safe_float(latest.body_fat_pct) - safe_float(first.body_fat_pct)
                    if safe_float(latest.body_fat_pct) is not None
                    and safe_float(first.body_fat_pct) is not None
                    else None
                ),
                "muscle_mass_change": (
                    safe_float(latest.muscle_mass) - safe_float(first.muscle_mass)
                    if safe_float(latest.muscle_mass) is not None
                    and safe_float(first.muscle_mass) is not None
                    else None
                ),
                "first_date": first.date,
                "latest_date": latest.date,
            }
