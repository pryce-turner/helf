"""Tests for `observation`, the tall `metric` table, and the views over them."""

import sqlite3
from datetime import datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import app.database as database
from app.db.models import Metric, Observation
from app.models.body_composition import BodyComposition


def _metric(session, **kwargs):
    """Record one value, creating (or reusing) its observation."""
    observed_at = kwargs.pop("observed_at", "2026-01-01 08:00:00.000000")
    source = kwargs.pop("source", "openscale")
    defaults = {"name": "body_weight_lb", "value": 190.0, "unit": "lb"}

    observation = (
        session.query(Observation)
        .filter_by(observed_at=observed_at, source=source)
        .one_or_none()
    )
    if observation is None:
        observation = Observation(
            observed_at=observed_at, source=source, created_at=datetime(2026, 1, 1)
        )
        session.add(observation)

    observation.metrics.append(Metric(**{**defaults, **kwargs}))
    session.commit()


@pytest.fixture()
def seeded(db_session):
    """The db_engine fixture already seeds metric_def; this just names it."""
    return db_session


class TestMetricConstraints:
    def test_date_is_derived_from_observed_at(self, seeded):
        """`date` lives on the observation - the instant is its property."""
        _metric(seeded, observed_at="2026-03-10 14:23:45.000000")

        assert seeded.query(Observation).one().date == "2026-03-10"

    def test_metrics_are_reachable_from_their_observation(self, seeded):
        """One act of measuring, several values."""
        _metric(seeded, name="body_weight_lb", value=190.0)
        _metric(seeded, name="body_fat_pct", value=23.7, unit="%")

        observation = seeded.query(Observation).one()
        assert {m.name for m in observation.metrics} == {
            "body_weight_lb",
            "body_fat_pct",
        }

    def test_deleting_an_observation_removes_its_metrics(self, seeded):
        """ON DELETE CASCADE: `DELETE /{id}` names the observation only."""
        _metric(seeded, name="body_weight_lb", value=190.0)
        _metric(seeded, name="body_fat_pct", value=23.7, unit="%")

        seeded.delete(seeded.query(Observation).one())
        seeded.commit()

        assert seeded.query(Metric).count() == 0

    def test_unknown_metric_name_is_rejected(self, seeded):
        """metric_def is the vocabulary, enforced in the schema.

        Both writers hit it - the app and the agent's MCP write tool - which is
        the point of putting it in the database rather than in Python.
        """
        with pytest.raises(IntegrityError):
            _metric(seeded, name="not_a_defined_metric")
        seeded.rollback()

    def test_same_quantity_from_two_sources_coexists(self, seeded):
        """The constraint keeps sources separate rather than overwriting.

        A DEXA scan and a bioimpedance reading of body fat on the same day are
        two measurements, not one refining the other.
        """
        _metric(seeded, name="body_fat_pct", value=23.7, unit="%", source="openscale")
        _metric(seeded, name="body_fat_pct", value=16.6, unit="%", source="bodyspec")

        assert seeded.query(Metric).count() == 2

    def test_duplicate_observation_from_one_source_is_rejected(self, seeded):
        _metric(seeded)
        with pytest.raises(IntegrityError):
            _metric(seeded, value=999.0)
        seeded.rollback()

    def test_row_with_no_value_at_all_is_rejected(self, seeded):
        with pytest.raises(IntegrityError):
            _metric(seeded, value=None)
        seeded.rollback()

    def test_text_value_satisfies_the_check(self, seeded):
        _metric(seeded, value=None, text_value="refused to stand still")

        assert seeded.query(Metric).one().text_value == "refused to stand still"


class TestViews:
    @pytest.fixture()
    def migrated(self, db_engine):
        return db_engine

    @staticmethod
    def _insert(engine, rows):
        with engine.begin() as conn:
            for observed_at, name, value, source in rows:
                conn.execute(
                    text(
                        "INSERT OR IGNORE INTO observation "
                        "(observed_at, source, created_at) VALUES (:o, :s, :o)"
                    ),
                    {"o": observed_at, "s": source},
                )
                conn.execute(
                    text(
                        "INSERT INTO metric (observation_id, name, value, unit) "
                        "SELECT id, :n, :v, 'x' FROM observation "
                        "WHERE observed_at = :o AND source = :s"
                    ),
                    {"o": observed_at, "n": name, "v": value, "s": source},
                )

    def test_coverage_distinguishes_undefined_from_unrecorded(self, migrated):
        """n_rows = 0 is the difference between "no data" and "no change"."""
        with migrated.connect() as conn:
            coverage = dict(
                conn.execute(text("SELECT name, n_rows FROM v_metric_coverage")).all()
            )

        # Seeded but deliberately unpopulated until the food/journal work lands.
        assert coverage["alcohol_units"] == 0
        assert coverage["mood"] == 0
        assert coverage["sleep_hours"] == 0
        assert "body_weight_lb" in coverage

    def test_daily_view_averages_repeated_weigh_ins(self, migrated):
        """Two readings in a day average; MAX would report the heavier one.

        Real history has 30 such days, 13 with genuinely different readings and
        spreads up to 4 lb, so this is not hypothetical.
        """
        self._insert(
            migrated,
            [
                ("2026-01-01 07:00:00", "body_weight_lb", 200.0, "openscale"),
                ("2026-01-01 19:00:00", "body_weight_lb", 204.0, "openscale"),
            ],
        )

        with migrated.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT weight, n_measurements FROM v_body_comp_daily "
                    "WHERE date = '2026-01-01' AND source = 'openscale'"
                )
            ).one()

        assert row.weight == pytest.approx(202.0)
        assert row.n_measurements == 2

    def test_daily_view_keeps_sources_apart(self, migrated):
        """Grouping on source is what stops DEXA and bioimpedance merging."""
        self._insert(
            migrated,
            [
                # Each observation carries a weight because the views define a
                # body-composition measurement as one that has a body weight -
                # a scale reading and a DEXA scan both do. Body fat alone would
                # be excluded, which is the point of that restriction.
                ("2026-02-01 07:00:00", "body_weight_lb", 200.0, "openscale"),
                ("2026-02-01 07:00:00", "body_fat_pct", 23.7, "openscale"),
                ("2026-02-01 09:00:00", "body_weight_lb", 193.3, "bodyspec"),
                ("2026-02-01 09:00:00", "body_fat_pct", 16.6, "bodyspec"),
            ],
        )

        with migrated.connect() as conn:
            rows = dict(
                conn.execute(
                    text(
                        "SELECT source, body_fat_pct FROM v_body_comp_daily "
                        "WHERE date = '2026-02-01'"
                    )
                ).all()
            )

        assert rows == {"openscale": pytest.approx(23.7), "bodyspec": pytest.approx(16.6)}

    def test_measurement_view_preserves_full_grain(self, migrated):
        """One row per weigh-in, so nothing collapses."""
        self._insert(
            migrated,
            [
                ("2026-01-01 07:00:00", "body_weight_lb", 200.0, "openscale"),
                ("2026-01-01 19:00:00", "body_weight_lb", 204.0, "openscale"),
            ],
        )

        with migrated.connect() as conn:
            weights = [
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT weight FROM v_body_comp_measurements "
                        "WHERE date = '2026-01-01' ORDER BY observed_at"
                    )
                ).all()
            ]

        assert weights == [200.0, 204.0]

    def test_muscle_mass_column_is_fed_from_muscle_pct(self, migrated):
        """The legacy column name is preserved; the metric name is honest.

        An earlier draft mapped this from `muscle_mass_lb`, which nothing seeds,
        so the column would have been silently NULL on every row.
        """
        self._insert(
            migrated,
            [
                ("2026-01-05 07:00:00", "body_weight_lb", 200.0, "openscale"),
                ("2026-01-05 07:00:00", "muscle_pct", 39.1, "openscale"),
            ],
        )

        with migrated.connect() as conn:
            value = conn.execute(
                text(
                    "SELECT muscle_mass FROM v_body_comp_daily "
                    "WHERE date = '2026-01-05'"
                )
            ).scalar()

        assert value == pytest.approx(39.1)

    def test_an_observation_with_no_weight_is_not_a_measurement(self, migrated):
        """A mood entry must not surface as a body-composition measurement.

        The views used to emit a row for any observation carrying any metric,
        which was harmless only while every observation was a weigh-in.
        `metric_def` now defines mood, sleep and eleven DEXA quantities, and
        `BodyComposition.weight` is a required float - so a weightless
        observation in the list is a 500 on the whole endpoint, not one bad row.
        """
        self._insert(
            migrated,
            [
                ("2026-03-01 07:00:00", "body_weight_lb", 200.0, "openscale"),
                ("2026-03-01 21:00:00", "mood", 7.0, "manual"),
                ("2026-03-01 21:00:00", "sleep_hours", 7.5, "manual"),
            ],
        )

        with migrated.connect() as conn:
            measurements = conn.execute(
                text(
                    "SELECT source, weight FROM v_body_comp_measurements "
                    "WHERE date = '2026-03-01'"
                )
            ).all()
            daily = conn.execute(
                text(
                    "SELECT source FROM v_body_comp_daily "
                    "WHERE date = '2026-03-01'"
                )
            ).scalars().all()

        assert [(r.source, r.weight) for r in measurements] == [("openscale", 200.0)]
        assert daily == ["openscale"]

    def test_null_weight_would_break_the_response_model(self, migrated):
        """Proves the consequence the view is guarding against is real.

        Without this, the test above only asserts that a row is absent, with no
        evidence that its presence would matter.
        """
        self._insert(
            migrated, [("2026-03-02 21:00:00", "mood", 7.0, "manual")]
        )

        with migrated.connect() as conn:
            leaked = conn.execute(
                text(
                    "SELECT count(*) FROM v_body_comp_measurements "
                    "WHERE date = '2026-03-02'"
                )
            ).scalar_one()
        assert leaked == 0

        with pytest.raises(ValidationError):
            BodyComposition(
                doc_id=1,
                timestamp=datetime(2026, 3, 2, 21, 0),
                date="2026-03-02",
                weight=None,
                created_at=datetime(2026, 3, 2, 21, 0),
            )


def test_metric_def_seed_survives_migration(tmp_path, monkeypatch):
    """The vocabulary is created by migration, not by application code."""
    db_path = tmp_path / "seed.db"
    monkeypatch.setattr(database.settings, "db_path", db_path)

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(database.ALEMBIC_INI)), "head")

    raw = sqlite3.connect(db_path)
    names = {r[0] for r in raw.execute("SELECT name FROM metric_def")}
    mood = raw.execute(
        "SELECT ref_low, ref_high FROM metric_def WHERE name = 'mood'"
    ).fetchone()
    raw.close()

    assert {"body_weight_lb", "body_fat_pct", "muscle_pct", "water_pct"} <= names
    assert mood == (1.0, 10.0)
