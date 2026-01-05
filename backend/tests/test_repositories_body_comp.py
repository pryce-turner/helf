import pytest
from datetime import datetime, timedelta

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
    assert stats["body_fat_change"] == -3
    assert stats["muscle_mass_change"] == 3
    assert stats["weight_change"] == pytest.approx(-9.0)
