from datetime import datetime, timedelta

import pytest

from app.utils.date_helpers import PACIFIC_TZ

pytestmark = pytest.mark.usefixtures("db_engine")


def test_body_comp_latest_and_create(client):
    empty = client.get("/api/body-composition/latest")
    assert empty.status_code == 404

    now = datetime.now(PACIFIC_TZ)
    payload = {
        "timestamp": now.isoformat(),
        "date": now.date().isoformat(),
        "weight": 80.5,
        "body_fat_pct": 18.5,
    }
    created = client.post("/api/body-composition/", json=payload)
    assert created.status_code == 201

    duplicate = client.post("/api/body-composition/", json=payload)
    assert duplicate.status_code == 409

    latest = client.get("/api/body-composition/latest")
    assert latest.status_code == 200
    assert latest.json()["weight"] == 80.5


def test_body_comp_trends_and_stats(client):
    now = datetime.now(PACIFIC_TZ)
    client.post(
        "/api/body-composition/",
        json={
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "date": (now - timedelta(days=1)).date().isoformat(),
            "weight": 80,
        },
    )
    client.post(
        "/api/body-composition/",
        json={
            "timestamp": now.isoformat(),
            "date": now.date().isoformat(),
            "weight": 81,
        },
    )

    trends = client.get("/api/body-composition/trends?days=30")
    assert trends.status_code == 200
    assert len(trends.json()["dates"]) == 2

    stats = client.get("/api/body-composition/stats")
    assert stats.status_code == 200
    assert stats.json()["total_measurements"] == 2


def test_trends_expose_and_filter_by_source(client, db_session):
    """A chart cannot avoid joining two instruments with a line unless the
    response tells it which points came from which."""
    from app.models.body_composition import BodyCompositionCreate
    from app.repositories.body_comp_repo import BodyCompositionRepository

    repo = BodyCompositionRepository()
    now = datetime.now(PACIFIC_TZ)
    for offset, source, weight in (
        (2, "openscale", 200.0),
        (1, "openscale", 198.0),
        (0, "bodyspec", 193.3),
    ):
        ts = now - timedelta(days=offset)
        repo.create(
            BodyCompositionCreate(
                timestamp=ts, date=ts.date().isoformat(), weight=weight
            ),
            source=source,
        )

    every = client.get("/api/body-composition/trends?days=30").json()
    assert every["sources"] == ["openscale", "openscale", "bodyspec"]
    assert len(every["dates"]) == len(every["sources"])

    dexa = client.get("/api/body-composition/trends?days=30&source=bodyspec").json()
    assert dexa["sources"] == ["bodyspec"]
    assert dexa["weights"] == [pytest.approx(193.3)]


def test_measurements_and_stats_report_their_source(client, db_session):
    from app.models.body_composition import BodyCompositionCreate
    from app.repositories.body_comp_repo import BodyCompositionRepository

    repo = BodyCompositionRepository()
    now = datetime.now(PACIFIC_TZ)
    for offset, source, weight, fat in (
        (2, "openscale", 200.0, 23.7),
        (1, "openscale", 198.0, 23.2),
        (0, "bodyspec", 193.3, 16.6),
    ):
        ts = now - timedelta(days=offset)
        repo.create(
            BodyCompositionCreate(
                timestamp=ts,
                date=ts.date().isoformat(),
                weight=weight,
                body_fat_pct=fat,
            ),
            source=source,
        )

    listed = client.get("/api/body-composition/").json()
    assert [m["source"] for m in listed] == ["bodyspec", "openscale", "openscale"]

    stats = client.get("/api/body-composition/stats").json()
    assert stats["latest_source"] == "bodyspec"
    assert stats["primary_source"] == "openscale"
    # Not -7.1: that is the gap between a bioimpedance estimate and a DEXA
    # measurement, not seven points of body fat lost in two days.
    assert stats["body_fat_change"] == pytest.approx(-0.5)
