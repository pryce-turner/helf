"""Body composition repository for database operations."""

from tinydb import Query
from datetime import datetime, timedelta
from typing import Optional

from app.database import get_table, BODY_COMP_TABLE
from app.models.body_composition import BodyCompositionCreate
from app.utils.date_helpers import get_current_datetime, parse_iso_timestamp, PACIFIC_TZ


class BodyCompositionRepository:
    """Repository for body composition data operations."""

    def __init__(self):
        self.table = get_table(BODY_COMP_TABLE)
        self.query = Query()

    def get_all(self, skip: int = 0, limit: int = 100) -> list[dict]:
        """Get all measurements with pagination."""
        measurements = self.table.all()
        measurements = [{**doc, 'doc_id': doc.doc_id} for doc in measurements]
        # Sort by timestamp descending (most recent first)
        measurements.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return measurements[skip:skip+limit]

    def get_by_id(self, doc_id: int) -> Optional[dict]:
        """Get a measurement by ID."""
        return self.table.get(doc_id=doc_id)

    def get_latest(self) -> Optional[dict]:
        """Get the most recent measurement."""
        measurements = self.table.all()
        if not measurements:
            return None

        measurements = [{**doc, 'doc_id': doc.doc_id} for doc in measurements]
        measurements.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return measurements[0]

    def get_by_date_range(self, start_date: str, end_date: str) -> list[dict]:
        """Get measurements within a date range."""
        measurements = self.table.search(
            (self.query.date >= start_date) & (self.query.date <= end_date)
        )
        measurements = [{**doc, 'doc_id': doc.doc_id} for doc in measurements]
        measurements.sort(key=lambda x: x.get('timestamp', ''))
        return measurements

    def get_recent(self, days: int = 30) -> list[dict]:
        """Get measurements from the last N days."""
        cutoff_date = (
            datetime.now(PACIFIC_TZ).date() - timedelta(days=days)
        ).isoformat()

        measurements = self.table.search(self.query.date >= cutoff_date)
        measurements = [{**doc, 'doc_id': doc.doc_id} for doc in measurements]
        measurements.sort(key=lambda x: x.get('timestamp', ''))
        return measurements

    def create(self, measurement: BodyCompositionCreate) -> Optional[dict]:
        """Create a new measurement. Returns None if duplicate timestamp."""
        # Check for duplicate timestamp
        timestamp_str = measurement.timestamp.isoformat()
        existing = self.table.search(self.query.timestamp == timestamp_str)
        if existing:
            return None  # Duplicate, skip

        now = get_current_datetime()
        measurement_dict = measurement.model_dump(exclude_none=False)
        measurement_dict['timestamp'] = timestamp_str
        measurement_dict['created_at'] = now.isoformat()

        doc_id = self.table.insert(measurement_dict)
        return self.table.get(doc_id=doc_id)

    def delete(self, doc_id: int) -> bool:
        """Delete a measurement."""
        removed = self.table.remove(doc_ids=[doc_id])
        return len(removed) > 0

    def get_stats(self) -> dict:
        """Get summary statistics."""
        measurements = self.table.all()
        if not measurements:
            return {
                'total_measurements': 0,
                'latest_weight': None,
                'latest_body_fat': None,
                'latest_muscle_mass': None,
                'weight_change': None,
                'body_fat_change': None,
                'muscle_mass_change': None,
                'first_date': None,
                'latest_date': None,
            }

        measurements = [{**doc, 'doc_id': doc.doc_id} for doc in measurements]
        # Sort by timestamp
        measurements.sort(key=lambda x: x.get('timestamp', ''))

        first = measurements[0]
        latest = measurements[-1]

        # Calculate 30-day average weight change
        now = datetime.now(PACIFIC_TZ)
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)

        # Get measurements for last 30 days
        last_30_days = [
            m for m in measurements
            if parse_iso_timestamp(m['timestamp']) >= thirty_days_ago
        ]

        # Get measurements for days 31-60
        prev_30_days = [
            m for m in measurements
            if sixty_days_ago <= parse_iso_timestamp(m['timestamp']) < thirty_days_ago
        ]

        def calculate_avg_weight(measurement_list):
            weights = [m.get('weight') for m in measurement_list if m.get('weight')]
            return sum(weights) / len(weights) if weights else None

        avg_weight_last_30 = calculate_avg_weight(last_30_days)
        avg_weight_prev_30 = calculate_avg_weight(prev_30_days)

        weight_change = None
        if avg_weight_last_30 is not None and avg_weight_prev_30 is not None:
            weight_change = avg_weight_last_30 - avg_weight_prev_30

        def safe_float(value):
            try:
                return float(value) if value else None
            except (ValueError, TypeError):
                return None

        return {
            'total_measurements': len(measurements),
            'latest_weight': safe_float(latest.get('weight')),
            'latest_body_fat': safe_float(latest.get('body_fat_pct')),
            'latest_muscle_mass': safe_float(latest.get('muscle_mass')),
            'weight_change': weight_change,
            'body_fat_change': (
                safe_float(latest.get('body_fat_pct')) - safe_float(first.get('body_fat_pct'))
                if safe_float(latest.get('body_fat_pct')) and safe_float(first.get('body_fat_pct'))
                else None
            ),
            'muscle_mass_change': (
                safe_float(latest.get('muscle_mass')) - safe_float(first.get('muscle_mass'))
                if safe_float(latest.get('muscle_mass')) and safe_float(first.get('muscle_mass'))
                else None
            ),
            'first_date': first.get('date'),
            'latest_date': latest.get('date'),
        }
