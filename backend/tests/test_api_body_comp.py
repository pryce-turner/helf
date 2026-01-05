import pytest
from datetime import datetime, timedelta

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
