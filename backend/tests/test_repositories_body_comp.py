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


class TestDualWriteToMetric:
    """Every body_composition write is mirrored into the tall `metric` table.

    The dual-write window: both tables are maintained until the read path moves
    onto the views (docs/plans/0003-units-and-metrics.md §4).
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

    def test_observed_at_matches_body_composition_timestamp_exactly(self, db_session):
        """Byte-identical, or new rows will not line up with the backfill.

        `metric.observed_at` is TEXT and the a3 backfill copied the stored
        timestamp verbatim. A different rendering would silently fork the series
        and stop UNIQUE(observed_at, name, source) from deduplicating.
        """
        repo = BodyCompositionRepository()
        ts = datetime(2026, 6, 2, 8, 15, 30, tzinfo=PACIFIC_TZ)
        repo.create(
            BodyCompositionCreate(timestamp=ts, date="2026-06-02", weight=190.0)
        )

        stored_ts = db_session.execute(
            text("SELECT timestamp FROM body_composition")
        ).scalar()
        observed_at = db_session.execute(
            text("SELECT DISTINCT observed_at FROM observation")
        ).scalar()

        assert observed_at == stored_ts

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

    def test_duplicate_timestamp_mirrors_nothing(self, db_session):
        """A rejected measurement must not leave metric rows behind."""
        repo = BodyCompositionRepository()
        ts = datetime(2026, 6, 6, 7, 0, tzinfo=PACIFIC_TZ)
        payload = BodyCompositionCreate(timestamp=ts, date="2026-06-06", weight=190.0)

        assert repo.create(payload) is not None
        assert repo.create(payload) is None

        assert db_session.execute(text("SELECT count(*) FROM metric")).scalar() == 1

    def test_delete_removes_mirrored_rows(self, db_session):
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

    def test_primary_write_commits_before_the_mirror_is_attempted(
        self, db_session, monkeypatch
    ):
        """Ordering: the measurement is durable before mirroring starts.

        openScale does not retransmit, so a dropped reading is gone for good. A
        divergence between the two tables is recoverable by re-running the
        backfill; that asymmetry is why the mirror commits separately.
        """
        repo = BodyCompositionRepository()

        def boom(*_args, **_kwargs):
            raise RuntimeError("metric table is on fire")

        monkeypatch.setattr(repo, "_mirror_to_metric", boom)

        with pytest.raises(RuntimeError):
            repo.create(
                BodyCompositionCreate(
                    timestamp=datetime(2026, 6, 8, 7, 0, tzinfo=PACIFIC_TZ),
                    date="2026-06-08",
                    weight=190.0,
                )
            )

        assert (
            db_session.execute(text("SELECT count(*) FROM body_composition")).scalar()
            == 1
        )

    def test_real_mirror_failure_is_swallowed_and_logged(
        self, db_session, monkeypatch, caplog
    ):
        """A genuine database error in the mirror must not reach the caller.

        Simulated by pointing the mirror at a metric name `metric_def` does not
        define, which is a real foreign key violation rather than a stubbed
        exception.
        """
        import app.repositories.body_comp_repo as repo_module

        monkeypatch.setattr(
            repo_module, "METRIC_COLUMNS", [("weight", "undefined_metric", "lb")]
        )
        repo = BodyCompositionRepository()

        created = repo.create(
            BodyCompositionCreate(
                timestamp=datetime(2026, 6, 9, 7, 0, tzinfo=PACIFIC_TZ),
                date="2026-06-09",
                weight=190.0,
            )
        )

        assert created is not None
        assert (
            db_session.execute(text("SELECT count(*) FROM body_composition")).scalar()
            == 1
        )
        assert db_session.execute(text("SELECT count(*) FROM metric")).scalar() == 0
        assert "Failed to mirror measurement" in caplog.text


class TestMirrorReconciliation:
    """The drift detector for the non-fatal mirror.

    A check that only ever reports "in sync" is worthless, so each failure mode
    is provoked rather than assumed.
    """

    @staticmethod
    def _measure(repo, day, **fields):
        ts = datetime(2026, 7, day, 7, 0, tzinfo=PACIFIC_TZ)
        return repo.create(
            BodyCompositionCreate(
                timestamp=ts,
                date=ts.date().isoformat(),
                weight=190.0,
                body_fat_pct=23.0,
                **fields,
            )
        )

    def test_reports_in_sync_after_normal_writes(self):
        repo = BodyCompositionRepository()
        self._measure(repo, 1)
        self._measure(repo, 2)

        report = repo.reconcile_mirror()
        assert report["in_sync"] is True
        assert report["expected_rows"] == report["mirrored_rows"] == 4

    def test_detects_a_mirror_that_never_ran(self, db_session):
        """The exact consequence of a swallowed mirror failure."""
        repo = BodyCompositionRepository()
        self._measure(repo, 3)
        db_session.execute(text("DELETE FROM metric"))
        db_session.commit()

        report = repo.reconcile_mirror()
        assert report["in_sync"] is False
        assert report["missing"] == 2
        assert report["sample"]["missing"]

    def test_detects_a_diverged_value(self, db_session):
        repo = BodyCompositionRepository()
        self._measure(repo, 4)
        db_session.execute(
            text("UPDATE metric SET value = 999 WHERE name = 'body_weight_lb'")
        )
        db_session.commit()

        report = repo.reconcile_mirror()
        assert report["in_sync"] is False
        assert report["mismatched"] == 1

    def test_detects_an_orphaned_metric_row(self, db_session):
        """A metric row with no measurement behind it - deletion gone wrong."""
        repo = BodyCompositionRepository()
        created = self._measure(repo, 5)
        db_session.execute(
            text("DELETE FROM body_composition WHERE id = :i"),
            {"i": created["doc_id"]},
        )
        db_session.commit()

        report = repo.reconcile_mirror()
        assert report["in_sync"] is False
        assert report["orphaned"] == 2

    def test_ignores_metrics_that_are_not_mirrored_columns(self, db_session):
        """Rows from other sources are not this check's business.

        A DEXA import or a journal entry writes metrics that have no
        body_composition row by design; flagging them as orphans would make the
        check cry wolf.
        """
        repo = BodyCompositionRepository()
        self._measure(repo, 6)
        # `mood` is already defined - the migration seeds it as a reserved
        # metric awaiting the journal work.
        db_session.execute(
            text(
                "INSERT INTO observation (observed_at, source, created_at) "
                "VALUES ('2026-07-06 07:00:00.000000', 'journal', '2026-07-06')"
            )
        )
        db_session.execute(
            text(
                "INSERT INTO metric (observation_id, name, value, unit) "
                "SELECT id, 'mood', 7, '1-10' FROM observation WHERE source='journal'"
            )
        )
        db_session.commit()

        assert repo.reconcile_mirror()["in_sync"] is True


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

    def test_reads_are_served_from_the_view(self, db_session):
        """Emptying the legacy table must not change what reads return.

        The sharpest available proof that the view is the source: nothing else
        would survive body_composition being gone.
        """
        repo = BodyCompositionRepository()
        self._create(repo, 1)
        self._create(repo, 2)

        db_session.execute(text("DELETE FROM body_composition"))
        db_session.commit()

        assert len(repo.get_all()) == 2
        assert repo.get_latest()["weight"] == pytest.approx(192.0)
        assert repo.get_stats()["total_measurements"] == 2

    def test_doc_id_round_trips_through_delete(self, db_session):
        """The id a read hands out must be the id delete accepts.

        Reads return `observation.id`; `body_composition.id` is a different
        sequence that disagreed on 77 of the 150 production rows. Treating one
        as the other deletes a different measurement than the user asked for.
        """
        repo = BodyCompositionRepository()
        self._create(repo, 3)
        self._create(repo, 4)

        # Force the two sequences apart so a coincidental match cannot pass.
        db_session.execute(text("UPDATE body_composition SET id = id + 500"))
        db_session.commit()

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
