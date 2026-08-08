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


class TestBodySpecSyncEndpoint:
    """The token arrives in a header, is forwarded, and is never stored."""

    @staticmethod
    def _payload():
        from tests.test_services_bodyspec import SCAN

        return SCAN

    def test_a_rejected_token_is_a_401_not_a_500(self, client, monkeypatch):
        """The one error the user will actually hit. A 500 would send them
        debugging Helf instead of pasting a fresh token."""
        from app.api import body_comp
        from app.services.bodyspec_client import BodySpecAuthError

        class Expired:
            def list_results(self, token):
                raise BodySpecAuthError("BodySpec rejected the token.")

        monkeypatch.setattr(body_comp, "BodySpecClient", lambda: Expired())

        response = client.post(
            "/api/body-composition/sync/bodyspec",
            headers={"Authorization": "Bearer expired-nonsense"},
        )
        assert response.status_code == 401
        assert "token" in response.json()["detail"].lower()

    def test_upstream_failure_is_a_502(self, client, monkeypatch):
        from app.api import body_comp
        from app.services.bodyspec_client import BodySpecError

        class Broken:
            def list_results(self, token):
                raise BodySpecError("BodySpec returned 503 for results/")

        monkeypatch.setattr(body_comp, "BodySpecClient", lambda: Broken())

        response = client.post(
            "/api/body-composition/sync/bodyspec",
            headers={"Authorization": "Bearer whatever"},
        )
        assert response.status_code == 502

    def test_a_missing_or_malformed_header_is_rejected(self, client):
        assert client.post("/api/body-composition/sync/bodyspec").status_code == 422

        for header in ("", "Bearer", "Basic abc123"):
            response = client.post(
                "/api/body-composition/sync/bodyspec",
                headers={"Authorization": header},
            )
            assert response.status_code == 401, header

    def test_a_successful_sync_reports_counts_and_is_idempotent(
        self, client, monkeypatch
    ):
        from app.api import body_comp

        scan = self._payload()

        class Stub:
            def list_results(self, token):
                assert token == "a-real-looking-token"
                return [{"result_id": "res_abc123"}]

            def fetch_scan(self, token, result_id):
                return scan

        monkeypatch.setattr(body_comp, "BodySpecClient", lambda: Stub())
        headers = {"Authorization": "Bearer a-real-looking-token"}

        first = client.post("/api/body-composition/sync/bodyspec", headers=headers)
        assert first.status_code == 200
        assert first.json() == {
            "scans_found": 1,
            "imported": 1,
            "skipped": 1 - 1,
            "metrics_written": 13,
        }

        second = client.post("/api/body-composition/sync/bodyspec", headers=headers)
        assert second.json() == {
            "scans_found": 1,
            "imported": 0,
            "skipped": 1,
            "metrics_written": 0,
        }

        # And the scan is now readable through the normal body-composition API,
        # tagged so nothing averages it with a bioimpedance reading.
        listed = client.get("/api/body-composition/").json()
        assert [m["source"] for m in listed] == ["bodyspec"]
        assert listed[0]["weight"] == pytest.approx(193.2793, abs=1e-3)

    def test_the_token_is_not_written_to_the_database(self, client, monkeypatch):
        """Structural, not a matter of restricting views: the MCP `query` tool
        reads the whole schema, so a token anywhere in it is readable."""
        from app.api import body_comp

        scan = self._payload()
        token = "tok_ThisMustNotBeFoundAnywhereInTheDatabase"

        class Stub:
            def list_results(self, t):
                return [{"result_id": "res_abc123"}]

            def fetch_scan(self, t, result_id):
                return scan

        monkeypatch.setattr(body_comp, "BodySpecClient", lambda: Stub())
        client.post(
            "/api/body-composition/sync/bodyspec",
            headers={"Authorization": f"Bearer {token}"},
        )

        from sqlalchemy import text as sql

        import app.database as database

        with database.SessionLocal() as session:
            tables = session.execute(
                sql("SELECT name FROM sqlite_master WHERE type='table'")
            ).scalars().all()
            for table in tables:
                columns = session.execute(
                    sql(f'SELECT * FROM "{table}" LIMIT 0')  # noqa: S608
                ).keys()
                for column in columns:
                    # Quoted: `workouts` has a column called `order`.
                    hits = session.execute(
                        sql(
                            f'SELECT count(*) FROM "{table}" '  # noqa: S608
                            f'WHERE CAST("{column}" AS TEXT) LIKE :needle'
                        ),
                        {"needle": f"%{token}%"},
                    ).scalar_one()
                    assert hits == 0, f"token found in {table}.{column}"
