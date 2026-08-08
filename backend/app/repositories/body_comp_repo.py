"""Body composition repository for database operations."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, text

from app.database import SessionLocal
from app.db.models import BodyComposition, Metric, Observation
from app.models.body_composition import BodyCompositionCreate
from app.utils.date_helpers import (
    PACIFIC_TZ,
    get_current_datetime,
    parse_iso_timestamp,
)
from app.utils.units import CANONICAL_WEIGHT_UNIT

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

# Sources whose observations mirror a `body_composition` row. `body_composition`
# does not record which one produced a given measurement, so deletion and
# reconciliation match on the instant and restrict to these - leaving a DEXA
# import or a journal entry at the same instant alone.
MIRROR_SOURCES = ("manual", "openscale")


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

    def _serialize(self, measurement: BodyComposition, source: str) -> dict:
        return {
            "doc_id": measurement.id,
            "timestamp": measurement.timestamp,
            "date": measurement.date,
            "weight": measurement.weight,
            "weight_unit": CANONICAL_WEIGHT_UNIT,
            "body_fat_pct": measurement.body_fat_pct,
            "muscle_mass": measurement.muscle_mass,
            "bmi": measurement.bmi,
            "water_pct": measurement.water_pct,
            "bone_mass": measurement.bone_mass,
            "visceral_fat": measurement.visceral_fat,
            "metabolic_age": measurement.metabolic_age,
            "protein_pct": measurement.protein_pct,
            "created_at": measurement.created_at,
            "source": source,
        }

    @staticmethod
    def _from_view(row) -> dict:
        """Shape a `v_body_comp_measurements` row like `_serialize` does.

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
            "bone_mass": row.bone_mass,
            "visceral_fat": row.visceral_fat,
            "metabolic_age": row.metabolic_age,
            "protein_pct": row.protein_pct,
            "created_at": parse_iso_timestamp(row.created_at),
        }

    def _read_measurements(self, where: str = "", order: str = "DESC", **params):
        """Query the per-measurement view.

        Deliberately `v_body_comp_measurements` and never `v_body_comp_daily`:
        the daily view collapses to one row per day, which for this history
        would silently drop 43 of 150 measurements.
        """
        clause = f"WHERE {where}" if where else ""
        with SessionLocal() as session:
            rows = session.execute(
                text(
                    f"SELECT * FROM v_body_comp_measurements {clause} "  # noqa: S608
                    f"ORDER BY observed_at {order}"
                    + (" LIMIT :limit OFFSET :skip" if "limit" in params else "")
                ),
                params,
            ).all()
        return [self._from_view(row) for row in rows]

    def get_all(self, skip: int = 0, limit: int = 100) -> list[dict]:
        """Get all measurements with pagination."""
        return self._read_measurements(order="DESC", limit=limit, skip=skip)

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
            serialized = self._serialize(new_measurement, source)

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
                observation = Observation(
                    observed_at=observed_at,
                    source=source,
                    created_at=measurement.created_at,
                )
                for column, metric_name, unit in METRIC_COLUMNS:
                    value = getattr(measurement, column)
                    if value is None:
                        continue
                    observation.metrics.append(
                        Metric(name=metric_name, value=value, unit=unit)
                    )
                session.add(observation)
                session.commit()
        except Exception:
            # Loud, but not fatal: the measurement itself is already safe.
            logger.exception(
                "Failed to mirror measurement %s into `metric`; "
                "body_composition is authoritative and can be re-backfilled",
                observed_at,
            )

    def reconcile_mirror(self) -> dict:
        """Compare `body_composition` against its `metric` mirror.

        The mirror is deliberately non-fatal (see `_mirror_to_metric`), which
        buys durability for the measurement at the cost of the two tables being
        able to drift apart silently. This is what makes that drift visible.

        `body_composition` is authoritative, so every difference is expressed as
        something the mirror is missing or has wrong - never the reverse.

        Returns counts plus a bounded sample, so it is safe to log or expose.
        """
        with SessionLocal() as session:
            measurements = session.execute(select(BodyComposition)).scalars().all()

            expected: dict[tuple[str, str], float] = {}
            for m in measurements:
                observed_at = _observed_at(m.timestamp)
                for column, metric_name, _unit in METRIC_COLUMNS:
                    value = getattr(m, column)
                    if value is not None:
                        expected[(observed_at, metric_name)] = float(value)

            actual = {
                (observed_at, name): value
                for observed_at, name, value in session.execute(
                    select(Observation.observed_at, Metric.name, Metric.value)
                    .join(Metric, Metric.observation_id == Observation.id)
                    .where(
                        Metric.name.in_([n for _c, n, _u in METRIC_COLUMNS]),
                        # Only observations that mirror a body_composition row.
                        # A DEXA import writes body_fat_pct too and would
                        # otherwise be reported as an orphan.
                        Observation.source.in_(MIRROR_SOURCES),
                    )
                ).all()
            }

        missing = sorted(k for k in expected if k not in actual)
        # Float comparison with a tolerance: the values round-trip through
        # SQLite REAL, so exact equality is not guaranteed to survive.
        mismatched = sorted(
            k
            for k, v in expected.items()
            if k in actual and abs(float(actual[k]) - v) > 1e-9
        )
        orphaned = sorted(k for k in actual if k not in expected)

        return {
            "expected_rows": len(expected),
            "mirrored_rows": len(actual),
            "missing": len(missing),
            "mismatched": len(mismatched),
            "orphaned": len(orphaned),
            "in_sync": not (missing or mismatched or orphaned),
            "sample": {
                "missing": missing[:5],
                "mismatched": mismatched[:5],
                "orphaned": orphaned[:5],
            },
        }

    def delete(self, doc_id: int) -> bool:
        """Delete a measurement and its legacy `body_composition` row.

        `doc_id` is an **`observation.id`**, because that is what the read path
        returns. It is emphatically not a `body_composition.id`: the two
        sequences disagree for 77 of the 150 existing rows, so treating one as
        the other deletes a different measurement than the user asked for.

        Metrics go with the observation via ON DELETE CASCADE.
        """
        with SessionLocal() as session:
            observation = session.get(Observation, doc_id)
            if observation is None:
                return False

            # One transaction: unlike create, a failure here loses nothing.
            # Matched on the instant, since body_composition has no observation
            # reference and is on its way out anyway.
            session.execute(
                text("DELETE FROM body_composition WHERE timestamp = :observed_at"),
                {"observed_at": observation.observed_at},
            )
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
