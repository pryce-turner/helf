from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.body_composition import BodyCompositionCreate
from app.repositories.body_comp_repo import BodyCompositionRepository
from app.utils.date_helpers import PACIFIC_TZ

pytestmark = pytest.mark.usefixtures("db_engine")


def test_body_comp_create_rejects_duplicate_timestamp():
    repo = BodyCompositionRepository()
    ts = datetime(2024, 1, 1, 12, 0, tzinfo=PACIFIC_TZ)
    created = repo.create(
        BodyCompositionCreate(
            timestamp=ts,
            date="2024-01-01",
            weight=80,
        )
    )
    assert created is not None
    duplicate = repo.create(
        BodyCompositionCreate(
            timestamp=ts,
            date="2024-01-01",
            weight=81,
        )
    )
    assert duplicate is None


def test_body_comp_get_latest_returns_most_recent():
    repo = BodyCompositionRepository()
    repo.create(
        BodyCompositionCreate(
            timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=PACIFIC_TZ),
            date="2024-01-01",
            weight=80,
        )
    )
    repo.create(
        BodyCompositionCreate(
            timestamp=datetime(2024, 1, 2, 10, 0, tzinfo=PACIFIC_TZ),
            date="2024-01-02",
            weight=81,
        )
    )

    latest = repo.get_latest()
    assert latest["date"] == "2024-01-02"


def test_body_comp_get_by_date_range_inclusive():
    repo = BodyCompositionRepository()
    repo.create(
        BodyCompositionCreate(
            timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=PACIFIC_TZ),
            date="2024-01-01",
            weight=80,
        )
    )
    repo.create(
        BodyCompositionCreate(
            timestamp=datetime(2024, 1, 3, 10, 0, tzinfo=PACIFIC_TZ),
            date="2024-01-03",
            weight=81,
        )
    )

    results = repo.get_by_date_range("2024-01-01", "2024-01-03")
    assert [r["date"] for r in results] == ["2024-01-01", "2024-01-03"]


def test_body_comp_get_recent_filters_by_cutoff():
    repo = BodyCompositionRepository()
    now = datetime.now(PACIFIC_TZ)
    repo.create(
        BodyCompositionCreate(
            timestamp=now - timedelta(days=5),
            date=(now - timedelta(days=5)).date().isoformat(),
            weight=80,
        )
    )
    repo.create(
        BodyCompositionCreate(
            timestamp=now - timedelta(days=40),
            date=(now - timedelta(days=40)).date().isoformat(),
            weight=90,
        )
    )

    recent = repo.get_recent(days=30)
    assert len(recent) == 1


def test_body_comp_stats_calculates_changes():
    repo = BodyCompositionRepository()
    now = datetime.now(PACIFIC_TZ)
    repo.create(
        BodyCompositionCreate(
            timestamp=now - timedelta(days=50),
            date=(now - timedelta(days=50)).date().isoformat(),
            weight=90,
            body_fat_pct=20,
            muscle_mass=40,
        )
    )
    repo.create(
        BodyCompositionCreate(
            timestamp=now - timedelta(days=20),
            date=(now - timedelta(days=20)).date().isoformat(),
            weight=82,
            body_fat_pct=18,
            muscle_mass=42,
        )
    )
    repo.create(
        BodyCompositionCreate(
            timestamp=now - timedelta(days=10),
            date=(now - timedelta(days=10)).date().isoformat(),
            weight=80,
            body_fat_pct=17,
            muscle_mass=43,
        )
    )

    stats = repo.get_stats()
    assert stats["total_measurements"] == 3
    assert stats["latest_weight"] == 80
    # All three changes are earliest-to-latest across all history.
    assert stats["body_fat_change"] == -3       # 17 - 20
    assert stats["muscle_mass_change"] == 3     # 43 - 40
    assert stats["weight_change"] == pytest.approx(-10.0)  # 80 - 90


def test_body_comp_stats_change_ignores_measurement_age():
    """A change is reported however long ago the last measurement was.

    The previous rolling-30-day definition returned None once the most recent
    reading aged past the window, so the card went blank on real data.
    """
    repo = BodyCompositionRepository()
    now = datetime.now(PACIFIC_TZ)
    for days_ago, weight in ((400, 200.0), (300, 190.0)):
        repo.create(
            BodyCompositionCreate(
                timestamp=now - timedelta(days=days_ago),
                date=(now - timedelta(days=days_ago)).date().isoformat(),
                weight=weight,
            )
        )

    assert repo.get_stats()["weight_change"] == pytest.approx(-10.0)


def test_body_comp_stats_change_is_none_for_single_measurement():
    """One data point is not a change."""
    repo = BodyCompositionRepository()
    now = datetime.now(PACIFIC_TZ)
    repo.create(
        BodyCompositionCreate(
            timestamp=now, date=now.date().isoformat(), weight=190.0
        )
    )

    assert repo.get_stats()["weight_change"] is None


def test_body_comp_stats_change_skips_rows_missing_that_metric():
    """A gap in the earliest row must not suppress the whole series.

    body_fat_pct is absent from the first measurement; the change is still
    computed from the two rows that have it.
    """
    repo = BodyCompositionRepository()
    now = datetime.now(PACIFIC_TZ)
    rows = [
        (30, 200.0, None),
        (20, 195.0, 22.0),
        (10, 190.0, 20.0),
    ]
    for days_ago, weight, fat in rows:
        repo.create(
            BodyCompositionCreate(
                timestamp=now - timedelta(days=days_ago),
                date=(now - timedelta(days=days_ago)).date().isoformat(),
                weight=weight,
                body_fat_pct=fat,
            )
        )

    stats = repo.get_stats()
    assert stats["weight_change"] == pytest.approx(-10.0)
    assert stats["body_fat_change"] == pytest.approx(-2.0)


class TestWritesLandInTheTallTables:
    """A measurement is an `observation` plus one `metric` per quantity.

    This was a *mirror* of `body_composition` until Plan 0010 retired the wide
    table; it is now simply where a measurement lives.
    """

    def test_create_mirrors_all_populated_columns(self, db_session):
        repo = BodyCompositionRepository()
        ts = datetime(2026, 6, 1, 7, 30, tzinfo=PACIFIC_TZ)
        repo.create(
            BodyCompositionCreate(
                timestamp=ts,
                date="2026-06-01",
                weight=190.0,
                body_fat_pct=23.7,
                muscle_mass=39.1,
                water_pct=51.0,
            )
        )

        rows = dict(
            db_session.execute(
                text("SELECT name, value FROM metric ORDER BY name")
            ).all()
        )
        assert rows == {
            "body_weight_lb": 190.0,
            "body_fat_pct": 23.7,
            "muscle_pct": 39.1,
            "water_pct": 51.0,
        }

    def test_observed_at_keeps_the_legacy_rendering_exactly(self, db_session):
        """Byte-identical to how history was written, or nothing lines up.

        `observation.observed_at` is TEXT and Plan 0003's backfill copied
        `body_composition.timestamp` verbatim - which is how SQLAlchemy's
        SQLite DATETIME renders. A different rendering would silently fork the
        series and stop UNIQUE (observed_at, source) from deduplicating a
        re-published MQTT reading.
        """
        repo = BodyCompositionRepository()
        ts = datetime(2026, 6, 2, 8, 15, 30, tzinfo=PACIFIC_TZ)
        repo.create(
            BodyCompositionCreate(timestamp=ts, date="2026-06-02", weight=190.0)
        )

        observed_at = db_session.execute(
            text("SELECT DISTINCT observed_at FROM observation")
        ).scalar()

        assert observed_at == "2026-06-02 08:15:30.000000"

    def test_absent_columns_are_not_mirrored(self, db_session):
        """A missing reading is absent, not zero."""
        repo = BodyCompositionRepository()
        ts = datetime(2026, 6, 3, 7, 0, tzinfo=PACIFIC_TZ)
        repo.create(
            BodyCompositionCreate(timestamp=ts, date="2026-06-03", weight=190.0)
        )

        names = {
            r[0] for r in db_session.execute(text("SELECT name FROM metric")).all()
        }
        assert names == {"body_weight_lb"}

    def test_source_defaults_to_manual_and_is_overridable(self, db_session):
        repo = BodyCompositionRepository()
        repo.create(
            BodyCompositionCreate(
                timestamp=datetime(2026, 6, 4, 7, 0, tzinfo=PACIFIC_TZ),
                date="2026-06-04",
                weight=190.0,
            )
        )
        repo.create(
            BodyCompositionCreate(
                timestamp=datetime(2026, 6, 5, 7, 0, tzinfo=PACIFIC_TZ),
                date="2026-06-05",
                weight=191.0,
            ),
            source="openscale",
        )

        sources = dict(
            db_session.execute(
                text("SELECT source, count(*) FROM observation GROUP BY source")
            ).all()
        )
        assert sources == {"manual": 1, "openscale": 1}

    def test_a_rejected_duplicate_writes_nothing(self, db_session):
        """A rejected measurement must not leave metric rows behind."""
        repo = BodyCompositionRepository()
        ts = datetime(2026, 6, 6, 7, 0, tzinfo=PACIFIC_TZ)
        payload = BodyCompositionCreate(timestamp=ts, date="2026-06-06", weight=190.0)

        assert repo.create(payload) is not None
        assert repo.create(payload) is None

        assert db_session.execute(text("SELECT count(*) FROM metric")).scalar() == 1

    def test_delete_removes_the_metrics_too(self, db_session):
        repo = BodyCompositionRepository()
        ts = datetime(2026, 6, 7, 7, 0, tzinfo=PACIFIC_TZ)
        created = repo.create(
            BodyCompositionCreate(
                timestamp=ts, date="2026-06-07", weight=190.0, body_fat_pct=23.0
            )
        )
        assert db_session.execute(text("SELECT count(*) FROM metric")).scalar() == 2

        assert repo.delete(created["doc_id"]) is True

        assert db_session.execute(text("SELECT count(*) FROM metric")).scalar() == 0

    def test_a_write_is_one_transaction(self, db_session, monkeypatch):
        """No half-written measurement, and no swallowed failure.

        Until Plan 0010 this was deliberately the opposite: `body_composition`
        committed first and the mirror ran afterwards in its own transaction
        that was allowed to fail, because a lost scale reading is unrecoverable
        while a divergent mirror is not. With one place to write, that
        asymmetry has nothing to trade off, so a failure is a failure.

        Provoked with a real foreign key violation - a metric name
        `metric_def` does not define - rather than a stubbed exception.
        """
        import app.repositories.body_comp_repo as repo_module

        monkeypatch.setattr(
            repo_module,
            "METRIC_COLUMNS",
            [("weight", "body_weight_lb", "lb"), ("body_fat_pct", "undefined", "%")],
        )

        with pytest.raises(Exception):  # noqa: B017 - IntegrityError from the FK
            BodyCompositionRepository().create(
                BodyCompositionCreate(
                    timestamp=datetime(2026, 6, 9, 7, 0, tzinfo=PACIFIC_TZ),
                    date="2026-06-09",
                    weight=190.0,
                    body_fat_pct=23.0,
                )
            )

        assert db_session.execute(text("SELECT count(*) FROM observation")).scalar() == 0
        assert db_session.execute(text("SELECT count(*) FROM metric")).scalar() == 0

    def test_two_instruments_at_one_instant_are_two_measurements(self):
        """Duplicate detection is per instrument now.

        It used to be `body_composition.timestamp` alone, so a manual entry and
        a scale reading at the same moment collided and the second was silently
        dropped. `UNIQUE (observed_at, source)` makes them two observations,
        which is what they are.
        """
        repo = BodyCompositionRepository()
        ts = datetime(2026, 6, 10, 7, 0, tzinfo=PACIFIC_TZ)
        payload = BodyCompositionCreate(timestamp=ts, date="2026-06-10", weight=190.0)

        assert repo.create(payload, source="manual") is not None
        assert repo.create(payload, source="openscale") is not None
        assert repo.create(payload, source="openscale") is None
        assert len(repo.get_all()) == 2

    def test_the_five_columns_that_never_had_a_home_now_have_one(self, db_session):
        """`bmi`, bone, visceral fat, metabolic age and protein were accepted by
        the API and written to a table nobody read. Plan 0010 §2."""
        repo = BodyCompositionRepository()
        repo.create(
            BodyCompositionCreate(
                timestamp=datetime(2026, 6, 11, 7, 0, tzinfo=PACIFIC_TZ),
                date="2026-06-11",
                weight=190.0,
                bmi=24.6,
                bone_mass_kg=3.2,
                visceral_fat=8,
                metabolic_age=31,
                protein_pct=17.4,
            )
        )

        rows = dict(
            db_session.execute(text("SELECT name, value FROM metric")).all()
        )
        assert rows["bmi"] == 24.6
        # kg, unconverted: `metric_def` already defines bone as kg for DEXA.
        assert rows["bone_mass_kg"] == 3.2
        assert rows["metabolic_age"] == 31

        # And they come back out, which they never did before.
        assert repo.get_latest()["bone_mass_kg"] == 3.2


class TestReadPathUsesTheViews:
    """Reads come from `v_body_comp_measurements`, not `body_composition`."""

    @staticmethod
    def _create(repo, day, **fields):
        ts = datetime(2026, 9, day, 7, 0, tzinfo=PACIFIC_TZ)
        return repo.create(
            BodyCompositionCreate(
                timestamp=ts,
                date=ts.date().isoformat(),
                weight=190.0 + day,
                body_fat_pct=23.0,
                **fields,
            )
        )

    def test_the_legacy_table_is_gone(self, db_session):
        """Plan 0010. The strongest form of "reads come from the view" is that
        there is nothing else left for them to come from."""
        repo = BodyCompositionRepository()
        self._create(repo, 1)
        self._create(repo, 2)

        assert (
            db_session.execute(
                text("SELECT count(*) FROM sqlite_master WHERE name='body_composition'")
            ).scalar()
            == 0
        )
        assert len(repo.get_all()) == 2
        assert repo.get_latest()["weight"] == pytest.approx(192.0)
        assert repo.get_stats()["total_measurements"] == 2

    def test_doc_id_round_trips_through_delete(self, db_session):
        """The id a read hands out must be the id delete accepts.

        Reads return `observation.id`. `body_composition.id` was a different
        sequence that disagreed on 77 of the 150 production rows, so treating
        one as the other deleted a different measurement than the user asked
        for. Retiring the table retired the hazard; this stays as the guard.
        """
        repo = BodyCompositionRepository()
        self._create(repo, 3)
        self._create(repo, 4)

        target = repo.get_latest()
        assert repo.delete(target["doc_id"]) is True

        remaining = repo.get_all()
        assert [m["doc_id"] for m in remaining] != [target["doc_id"]]
        assert len(remaining) == 1
        assert remaining[0]["weight"] == pytest.approx(193.0)

    def test_delete_of_unknown_id_reports_false(self):
        assert BodyCompositionRepository().delete(999999) is False

    def test_pagination_and_ordering_survive_the_move(self):
        repo = BodyCompositionRepository()
        for day in (5, 6, 7):
            self._create(repo, day)

        newest_first = repo.get_all(limit=2)
        assert [m["date"] for m in newest_first] == ["2026-09-07", "2026-09-06"]
        assert [m["date"] for m in repo.get_all(skip=2, limit=2)] == ["2026-09-05"]

    def test_date_range_is_inclusive_and_ascending(self):
        repo = BodyCompositionRepository()
        for day in (8, 9, 10):
            self._create(repo, day)

        found = repo.get_by_date_range("2026-09-08", "2026-09-09")
        assert [m["date"] for m in found] == ["2026-09-08", "2026-09-09"]

    def test_timestamps_come_back_as_datetimes(self):
        """The view stores TEXT; the response model needs datetimes."""
        repo = BodyCompositionRepository()
        self._create(repo, 11)

        latest = repo.get_latest()
        assert isinstance(latest["timestamp"], datetime)
        assert isinstance(latest["created_at"], datetime)


class TestSourcesAreNeverMixed:
    """openScale and BodySpec measure the same quantities and disagree.

    Bioimpedance reads body fat several percentage points above DEXA, and that
    gap is an artefact of the instruments, not of the body. Any figure that
    subtracts one from the other reports the gap as a change.
    """

    @staticmethod
    def _create(repo, day, source, **values):
        ts = datetime(2026, 5, day, 7, 0, tzinfo=PACIFIC_TZ)
        return repo.create(
            BodyCompositionCreate(
                timestamp=ts, date=ts.date().isoformat(), **values
            ),
            source=source,
        )

    def _mixed_history(self, repo):
        """Eight scale readings, then a DEXA scan reading much lower."""
        self._create(repo, 1, "openscale", weight=200.0, body_fat_pct=23.7)
        self._create(repo, 2, "openscale", weight=198.0, body_fat_pct=23.2)
        self._create(repo, 3, "bodyspec", weight=193.3, body_fat_pct=16.6)

    def test_measurements_carry_their_source(self):
        repo = BodyCompositionRepository()
        self._mixed_history(repo)

        assert [m["source"] for m in repo.get_all()] == [
            "bodyspec",
            "openscale",
            "openscale",
        ]

    def test_deltas_do_not_cross_instruments(self):
        """The whole point. Without this the DEXA scan reads as fat loss.

        Differencing across sources gives 16.6 - 23.7 = -7.1pp, which would be
        reported as seven points of body fat lost in two days. The honest
        figure is the openScale series' own -0.5pp.
        """
        repo = BodyCompositionRepository()
        self._mixed_history(repo)

        stats = repo.get_stats()
        assert stats["primary_source"] == "openscale"
        assert stats["body_fat_change"] == pytest.approx(-0.5)
        assert stats["weight_change"] == pytest.approx(-2.0)

    def test_latest_is_latest_whatever_produced_it(self):
        """A DEXA scan taken today is the best answer to "what do I weigh"."""
        repo = BodyCompositionRepository()
        self._mixed_history(repo)

        stats = repo.get_stats()
        assert stats["latest_source"] == "bodyspec"
        assert stats["latest_weight"] == pytest.approx(193.3)
        assert stats["latest_body_fat"] == pytest.approx(16.6)
        assert stats["total_measurements"] == 3

    def test_a_lone_scan_does_not_become_the_primary_series(self):
        """One measurement has no trend, and taking it as primary would blank
        three figures that months of scale data still support."""
        repo = BodyCompositionRepository()
        self._mixed_history(repo)

        assert repo.get_stats()["primary_source"] == "openscale"

    def test_primary_moves_once_the_new_instrument_has_a_trend(self):
        """Two scans make a DEXA trend, and it is the one worth reporting."""
        repo = BodyCompositionRepository()
        self._mixed_history(repo)
        self._create(repo, 4, "bodyspec", weight=191.0, body_fat_pct=15.9)

        stats = repo.get_stats()
        assert stats["primary_source"] == "bodyspec"
        assert stats["body_fat_change"] == pytest.approx(-0.7)

    def test_recent_can_be_restricted_to_one_instrument(self):
        repo = BodyCompositionRepository()
        self._mixed_history(repo)

        every = repo.get_recent(days=3650)
        assert {m["source"] for m in every} == {"openscale", "bodyspec"}

        dexa_only = repo.get_recent(days=3650, source="bodyspec")
        assert [m["source"] for m in dexa_only] == ["bodyspec"]
        assert [m["weight"] for m in dexa_only] == [pytest.approx(193.3)]
