"""Body composition repository for database operations."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, text

from app.database import SessionLocal
from app.db.models import Metric, Observation
from app.models.body_composition import BodyCompositionCreate
from app.utils.date_helpers import (
    PACIFIC_TZ,
    get_current_datetime,
    parse_iso_timestamp,
)
from app.utils.units import CANONICAL_WEIGHT_UNIT

logger = logging.getLogger(__name__)

# Request field -> (metric name, unit). This *was* the wide table's mirror map
# (Plan 0003's a3 backfill); with `body_composition` gone it is simply how a
# measurement is stored (Plan 0010).
#
# `muscle_mass` holds a percentage despite its name, so it maps to `muscle_pct`.
# `bone_mass_kg` is kg and is not converted: `metric_def` already defines it
# that way for DEXA, openScale reports kg, and one quantity under two names is
# what ADR-0003's naming rule exists to prevent.
METRIC_COLUMNS = [
    ("weight", "body_weight_lb", "lb"),
    ("body_fat_pct", "body_fat_pct", "%"),
    ("muscle_mass", "muscle_pct", "%"),
    ("water_pct", "water_pct", "%"),
    ("bmi", "bmi", "kg/m2"),
    ("bone_mass_kg", "bone_mass_kg", "kg"),
    ("visceral_fat", "visceral_fat", "index"),
    ("metabolic_age", "metabolic_age", "years"),
    ("protein_pct", "protein_pct", "%"),
]


def _observed_at(timestamp: datetime) -> str:
    """Render a timestamp the way SQLAlchemy's SQLite DATETIME did.

    `observation.observed_at` is TEXT and Plan 0003's backfill copied
    `body_composition.timestamp` verbatim, so new rows must use byte-identical
    formatting or they will not line up with eight months of history - and
    UNIQUE (observed_at, source), which is what deduplicates a re-published
    MQTT reading, is a textual comparison.
    """
    return timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")


class BodyCompositionRepository:
    """Repository for body composition data operations."""

    @staticmethod
    def _from_view(row) -> dict:
        """Shape a `v_body_comp_measurements` row for the response model.

        `observed_at` and `created_at` come back as TEXT because the view is
        over `observation`, whose columns are strings; the response model needs
        datetimes.
        """
        return {
            "doc_id": row.doc_id,
            "timestamp": parse_iso_timestamp(row.observed_at),
            "date": row.date,
            "source": row.source,
            "weight": row.weight,
            "weight_unit": CANONICAL_WEIGHT_UNIT,
            "body_fat_pct": row.body_fat_pct,
            "muscle_mass": row.muscle_mass,
            "bmi": row.bmi,
            "water_pct": row.water_pct,
            "bone_mass_kg": row.bone_mass_kg,
            "visceral_fat": row.visceral_fat,
            "metabolic_age": row.metabolic_age,
            "protein_pct": row.protein_pct,
            "created_at": parse_iso_timestamp(row.created_at),
        }

    # Whitelist, because the sort column is interpolated into the statement
    # below. The API validates too, but this is the layer the agent's raw SQL
    # never passes through, so it cannot be the only guard.
    SORT_COLUMNS = {"observed": "observed_at", "ingested": "created_at"}

    def _read_measurements(
        self,
        where: str = "",
        order: str = "DESC",
        sort: str = "observed",
        **params,
    ):
        """Query the per-measurement view.

        Deliberately `v_body_comp_measurements` and never `v_body_comp_daily`:
        the daily view collapses to one row per day, which for this history
        would silently drop 43 of 150 measurements.

        `sort` picks which of the two timestamps orders the result. They are
        different questions and both get asked: `observed` is when the weighing
        happened and is what a chart wants, `ingested` is when the row was
        written and is what an audit wants. A scale with a wrong clock puts
        them wildly out of step - the BF720 stamped a reading 2025-01-01 while
        it was being written in August 2026 - and finding that row means
        sorting by when it arrived, not by when it claims to be from.
        """
        clause = f"WHERE {where}" if where else ""
        column = self.SORT_COLUMNS.get(sort, "observed_at")
        with SessionLocal() as session:
            rows = session.execute(
                text(
                    f"SELECT * FROM v_body_comp_measurements {clause} "  # noqa: S608
                    f"ORDER BY {column} {order}"
                    + (" LIMIT :limit OFFSET :skip" if "limit" in params else "")
                ),
                params,
            ).all()
        return [self._from_view(row) for row in rows]

    def get_all(
        self, skip: int = 0, limit: int = 100, sort: str = "observed"
    ) -> list[dict]:
        """Get all measurements with pagination."""
        return self._read_measurements(
            order="DESC", sort=sort, limit=limit, skip=skip
        )

    def get_by_id(self, doc_id: int) -> dict | None:
        """Get a measurement by ID."""
        found = self._read_measurements(where="doc_id = :doc_id", doc_id=doc_id)
        return found[0] if found else None

    def get_latest(self) -> dict | None:
        """Get the most recent measurement."""
        found = self._read_measurements(order="DESC", limit=1, skip=0)
        return found[0] if found else None

    def get_by_date_range(self, start_date: str, end_date: str) -> list[dict]:
        """Get measurements within a date range."""
        return self._read_measurements(
            where="date >= :start AND date <= :end",
            order="ASC",
            start=start_date,
            end=end_date,
        )

    def get_recent(self, days: int = 30, source: str | None = None) -> list[dict]:
        """Get measurements from the last N days, optionally one instrument."""
        cutoff_date = (
            datetime.now(PACIFIC_TZ).date() - timedelta(days=days)
        ).isoformat()
        if source:
            return self._read_measurements(
                where="date >= :cutoff AND source = :source",
                order="ASC",
                cutoff=cutoff_date,
                source=source,
            )
        return self._read_measurements(
            where="date >= :cutoff", order="ASC", cutoff=cutoff_date
        )

    def create(
        self, measurement: BodyCompositionCreate, source: str = "manual"
    ) -> dict | None:
        """Record a measurement. Returns None if this instrument already has one
        at that instant.

        One transaction, one table pair. Until Plan 0010 this wrote the wide
        `body_composition` row first, committed, and mirrored into
        `observation`/`metric` afterwards in a separate transaction that was
        deliberately allowed to fail - a lost scale reading is unrecoverable
        (openScale does not retransmit) while a divergent mirror is not. With
        the wide table gone there is nothing to be asymmetric about.

        `source` keeps instruments of different accuracy apart, which is what
        stops a bioimpedance estimate and a DEXA scan of the same quantity from
        being averaged together. Defaults to "manual"; MQTT passes "openscale",
        matching the backfilled history.

        Duplicate detection is now per instrument. It used to be
        `body_composition.timestamp` alone, so a manual entry and a scale
        reading at the same instant collided and the second was silently
        dropped; `UNIQUE (observed_at, source)` makes them two observations,
        which is what they are.
        """
        observed_at = _observed_at(measurement.timestamp)

        with SessionLocal() as session:
            existing = session.execute(
                select(Observation).where(
                    Observation.observed_at == observed_at,
                    Observation.source == source,
                )
            ).scalar_one_or_none()
            if existing:
                return None

            observation = Observation(
                observed_at=observed_at,
                source=source,
                created_at=get_current_datetime(),
            )
            for field, metric_name, unit in METRIC_COLUMNS:
                value = getattr(measurement, field, None)
                if value is None:
                    continue
                observation.metrics.append(
                    Metric(name=metric_name, value=value, unit=unit)
                )
            session.add(observation)
            session.commit()
            doc_id = observation.id

        # Read back through the view rather than assembling a response by hand,
        # so what the caller receives is what every later read will return.
        return self.get_by_id(doc_id)

    def delete(self, doc_id: int) -> bool:
        """Delete a measurement.

        `doc_id` is an **`observation.id`**, because that is what the read path
        returns. It was emphatically not a `body_composition.id`: those two
        sequences disagreed for 77 of the 150 rows, so treating one as the
        other deleted a different measurement than the user asked for, silently,
        about half the time. That hazard retired with the table.

        Metrics go with the observation via ON DELETE CASCADE, and the audit
        log records each one, so a deletion is recoverable from `audit_log`
        rather than final.
        """
        with SessionLocal() as session:
            observation = session.get(Observation, doc_id)
            if observation is None:
                return False
            session.delete(observation)
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

        **Every delta is computed within one source.** Subtracting a DEXA body
        fat from a bioimpedance one measures the gap between two instruments,
        not a change in the body - the two disagree by several percentage
        points and always will. `primary_source` names the series the deltas
        describe, so the number on screen is never ambiguous about what it
        summarises.
        """
        # Reads the per-measurement view like every other read, so the page
        # cannot show a summary computed from one table beside a list from
        # another.
        measurements = self._read_measurements(order="ASC")
        if not measurements:
            return {
                "total_measurements": 0,
                "latest_weight": None,
                "latest_body_fat": None,
                "latest_muscle_mass": None,
                "latest_source": None,
                "weight_change": None,
                "body_fat_change": None,
                "muscle_mass_change": None,
                "primary_source": None,
                "first_date": None,
                "latest_date": None,
            }

        first = measurements[0]
        latest = measurements[-1]

        # The series the deltas describe: the most recently used instrument
        # that has enough history to have a trend at all. Two measurements is
        # the floor - a single DEXA scan says nothing about direction, and
        # letting it become the primary source would blank three figures that
        # eight months of scale data still support.
        #
        # It moves once a second source accumulates two points, which is
        # deliberate: the deltas should describe the instrument currently in
        # use, and `primary_source` in the response makes the switch visible
        # rather than silent.
        counts: dict[str, int] = {}
        for m in measurements:
            counts[m["source"]] = counts.get(m["source"], 0) + 1
        primary_source = next(
            (
                m["source"]
                for m in reversed(measurements)
                if counts.get(m["source"], 0) >= 2
            ),
            None,
        )
        primary = [m for m in measurements if m["source"] == primary_source]

        def safe_float(value):
            try:
                return float(value) if value is not None else None
            except (ValueError, TypeError):
                return None

        def change(field: str) -> float | None:
            """Earliest-to-latest delta for one metric, within `primary_source`.

            Scoped per metric rather than to the first and last rows overall: a
            single missing value in the earliest row would otherwise suppress a
            change that months of data support. That matters increasingly as
            sources with different column coverage are added - BodySpec
            populates fields openScale never does.

            Scoped to one source because a cross-source delta is not a change.
            openScale reads body fat several points above DEXA; differencing
            the two would report that gap as fat lost between the two dates.

            Returns None below two data points, where a change is undefined
            rather than zero.
            """
            values = [
                v for v in (safe_float(m[field]) for m in primary) if v is not None
            ]
            if len(values) < 2:
                return None
            return values[-1] - values[0]

        return {
            "total_measurements": len(measurements),
            # Latest is latest, whatever produced it - a DEXA scan taken today
            # is the best available answer to "what do I weigh".
            "latest_weight": safe_float(latest["weight"]),
            "latest_body_fat": safe_float(latest["body_fat_pct"]),
            "latest_muscle_mass": safe_float(latest["muscle_mass"]),
            "latest_source": latest["source"],
            "weight_change": change("weight"),
            "body_fat_change": change("body_fat_pct"),
            "muscle_mass_change": change("muscle_mass"),
            "primary_source": primary_source,
            "first_date": first["date"],
            "latest_date": latest["date"],
        }
