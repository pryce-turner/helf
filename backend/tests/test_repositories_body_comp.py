from datetime import datetime, timedelta

import pytest

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
