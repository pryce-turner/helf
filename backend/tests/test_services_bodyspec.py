"""Tests for the BodySpec client and the DEXA import.

Numbers throughout are the real 2026-03-10 scan as recorded in
docs/plans/0008-bodyspec-integration.md, so every assertion is checkable
against a payload that actually existed rather than against invented data that
agrees with the implementation by construction.
"""

import json
import logging
from datetime import datetime

import httpx
import pytest
from sqlalchemy import text

import app.database as database
from app.services import bodyspec_sync
from app.services.bodyspec_client import (
    BodySpecAuthError,
    BodySpecClient,
    BodySpecError,
)
from app.utils.date_helpers import PACIFIC_TZ

pytestmark = pytest.mark.usefixtures("db_engine")

TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.not-a-real-token.signature"

# The 2026-03-10 scan. fat + lean + bone = 14.51 + 69.61 + 3.55 = 87.67 exactly.
SCAN = {
    "scan_info": {
        "result_id": "res_abc123",
        "acquire_time": "2026-03-10T09:14:00",
        "scanner_model": "Horizon A",
        "patient_intake": {
            "age_years": 38,
            "height_cm": 180.3,
            # Deliberately different from total_mass_kg. Must not be promoted.
            "weight_kg": 86.2,
        },
    },
    "composition": {
        "result_id": "res_abc123",
        "total": {
            "fat_mass_kg": 14.51,
            "lean_mass_kg": 69.61,
            "bone_mass_kg": 3.55,
            "total_mass_kg": 87.67,
            "tissue_fat_pct": 17.25,
            "region_fat_pct": 16.55,
        },
        "regions": {"android": {"fat_mass_kg": 1.07}},
        "android_gynoid_ratio": 1.02,
    },
    "bone_density": {"total": {"bone_mineral_density": 1.31}},
    "visceral_fat": {"vat_mass_kg": 0.42, "vat_volume_cm3": 442},
    "rmr": {
        "estimates": [
            {"formula": "Cunningham (1980)", "kcal_per_day": 2110},
            {"formula": "Mifflin-St. Jeor (1990)", "kcal_per_day": 1854},
        ]
    },
    "percentiles": {
        "metrics": {
            "total_lmi_kg_m2": {"value": 18.4, "percentile": 71},
            "limb_lmi_kg_m2": {"value": 8.9, "percentile": 85},
            "total_body_fat_pct": {"value": 16.6, "percentile": 34},
        }
    },
}


class FakeClient:
    """Stands in for BodySpecClient, recording what it was asked for."""

    def __init__(self, scans=None, fail_on=None):
        self._scans = scans if scans is not None else {"res_abc123": SCAN}
        self._fail_on = fail_on
        self.fetched: list[str] = []
        self.tokens_seen: list[str] = []

    def list_results(self, token):
        self.tokens_seen.append(token)
        return [{"result_id": rid} for rid in self._scans]

    def fetch_scan(self, token, result_id):
        self.tokens_seen.append(token)
        if self._fail_on == result_id:
            raise BodySpecAuthError("token expired mid-sync")
        self.fetched.append(result_id)
        return self._scans[result_id]


def _sync(client, token=TOKEN):
    return bodyspec_sync.sync(
        client=client,
        token=token,
        session_factory=database.SessionLocal,
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=PACIFIC_TZ),
    )


def _metrics():
    with database.SessionLocal() as session:
        return {
            row.name: row.value
            for row in session.execute(
                text(
                    "SELECT m.name, m.value FROM metric m "
                    "JOIN observation o ON o.id = m.observation_id "
                    "WHERE o.source = 'bodyspec'"
                )
            )
        }


class TestPromotion:
    def test_the_scan_lands_as_one_observation_and_one_document(self):
        result = _sync(FakeClient())

        assert result == {
            "scans_found": 1,
            "imported": 1,
            "skipped": 0,
            "metrics_written": 13,
        }

        with database.SessionLocal() as session:
            observations = session.execute(
                text(
                    "SELECT observed_at, date, source FROM observation "
                    "WHERE source = 'bodyspec'"
                )
            ).all()
            documents = session.execute(
                text("SELECT kind, external_id FROM document")
            ).all()

        assert len(observations) == 1
        assert observations[0].date == "2026-03-10"
        assert [tuple(d) for d in documents] == [("dexa_bodyspec", "res_abc123")]

    def test_body_weight_is_converted_to_pounds(self):
        _sync(FakeClient())
        # 87.67 kg * 2.20462262184878
        assert _metrics()["body_weight_lb"] == pytest.approx(193.2793, abs=1e-3)

    def test_intake_weight_is_not_promoted(self):
        """Two body weights from one scan would be two conflicting series.

        86.2 kg intake vs 87.67 kg measured - a 3.2 lb gap that would show up
        as a systematic offset depending on which one happened to be read.
        """
        _sync(FakeClient())
        assert _metrics()["body_weight_lb"] != pytest.approx(
            86.2 * 2.20462262184878, abs=1e-3
        )

    def test_ffm_includes_bone_and_is_not_lean_mass(self):
        """The easy way to get this wrong, and it propagates into RMR."""
        assert _sync(FakeClient())["imported"] == 1
        metrics = _metrics()
        assert metrics["ffm_kg"] == pytest.approx(73.16, abs=0.01)
        assert metrics["lean_mass_kg"] == pytest.approx(69.61)
        assert metrics["ffm_kg"] != pytest.approx(metrics["lean_mass_kg"])

    def test_rmr_is_katch_mcardle_over_fat_free_mass(self):
        """370 + 21.6 * 73.16 = 1950, not 1874 (which uses lean mass).

        The wrong input understates RMR by 76 kcal/day - plausible enough to
        go unnoticed and large enough to matter as a daily target.
        """
        _sync(FakeClient())
        rmr = _metrics()["rmr_kcal_per_day"]
        assert rmr == pytest.approx(1950.3, abs=0.5)
        assert rmr != pytest.approx(370 + 21.6 * 69.61, abs=0.5)

    def test_body_fat_comes_from_tissue_not_region(self):
        """17.25 excludes bone; 16.55 includes it. A percentage point apart."""
        _sync(FakeClient())
        assert _metrics()["body_fat_pct"] == pytest.approx(17.25)

    def test_percentile_values_are_promoted_but_not_percentiles(self):
        _sync(FakeClient())
        metrics = _metrics()
        assert metrics["total_lmi_kg_m2"] == pytest.approx(18.4)
        assert metrics["limb_lmi_kg_m2"] == pytest.approx(8.9)
        # 71 and 85 are the percentiles; neither should have been stored.
        assert 71 not in metrics.values()
        assert 85 not in metrics.values()

    def test_the_whole_payload_is_retained(self):
        """Promotion is lossy on purpose, so the raw must survive intact."""
        _sync(FakeClient())
        with database.SessionLocal() as session:
            raw = session.execute(text("SELECT raw FROM document")).scalar_one()

        stored = json.loads(raw)
        assert stored == SCAN
        # Specifically: things nothing promotes are still reachable.
        assert stored["rmr"]["estimates"][0]["kcal_per_day"] == 2110
        assert stored["composition"]["total"]["region_fat_pct"] == 16.55

    def test_a_broken_decomposition_aborts_rather_than_deriving_nonsense(self):
        """ffm feeds a calorie target; a payload that does not add up must not
        silently produce one."""
        broken = json.loads(json.dumps(SCAN))
        broken["composition"]["total"]["lean_mass_kg"] = 50.0

        with pytest.raises(ValueError, match="not the shape this import assumes"):
            _sync(FakeClient({"res_broken": broken}))

    def test_a_scan_with_no_acquire_time_is_refused(self):
        undated = json.loads(json.dumps(SCAN))
        del undated["scan_info"]["acquire_time"]

        with pytest.raises(ValueError, match="no scan_info.acquire_time"):
            _sync(FakeClient({"res_undated": undated}))


class TestIdempotency:
    def test_a_second_sync_is_a_no_op(self):
        """The property most likely to break, whose failure is silent
        duplicate history."""
        first = _sync(FakeClient())
        assert first["imported"] == 1

        second = _sync(FakeClient())
        assert second == {
            "scans_found": 1,
            "imported": 0,
            "skipped": 1,
            "metrics_written": 0,
        }

        with database.SessionLocal() as session:
            assert session.execute(
                text("SELECT count(*) FROM document")
            ).scalar_one() == 1
            assert session.execute(
                text("SELECT count(*) FROM observation WHERE source='bodyspec'")
            ).scalar_one() == 1
            assert len(_metrics()) == 13

    def test_a_second_sync_does_not_refetch(self):
        """Skipping must happen before the HTTP calls, not after."""
        _sync(FakeClient())

        client = FakeClient()
        _sync(client)
        assert client.fetched == []

    def test_an_interrupted_sync_resumes(self):
        """A token expiring mid-sync must leave completed scans imported.

        This is what makes a 60-minute credential safe: nothing is corrupted
        by an interrupted run, so re-running with a fresh token finishes it.
        """
        second = json.loads(json.dumps(SCAN))
        second["scan_info"]["acquire_time"] = "2026-06-12T10:02:00"
        scans = {"res_abc123": SCAN, "res_second": second}

        with pytest.raises(BodySpecAuthError):
            _sync(FakeClient(scans, fail_on="res_second"))

        with database.SessionLocal() as session:
            assert session.execute(
                text("SELECT count(*) FROM document")
            ).scalar_one() == 1

        resumed = _sync(FakeClient(scans))
        assert resumed["imported"] == 1
        assert resumed["skipped"] == 1

        with database.SessionLocal() as session:
            assert session.execute(
                text("SELECT count(*) FROM observation WHERE source='bodyspec'")
            ).scalar_one() == 2


class TestTheImportedScanReachesTheReadPath:
    def test_it_becomes_a_measurement_carrying_its_source(self):
        _sync(FakeClient())

        with database.SessionLocal() as session:
            rows = session.execute(
                text(
                    "SELECT source, weight, body_fat_pct FROM "
                    "v_body_comp_measurements WHERE source = 'bodyspec'"
                )
            ).all()

        assert len(rows) == 1
        assert rows[0].weight == pytest.approx(193.2793, abs=1e-3)
        assert rows[0].body_fat_pct == pytest.approx(17.25)

    def test_the_derived_rmr_did_not_create_a_second_observation(self):
        """Plan 0008 §8 originally asked for source='derived', which would
        have produced a weightless observation and 500'd the endpoint."""
        _sync(FakeClient())

        with database.SessionLocal() as session:
            sources = session.execute(
                text("SELECT DISTINCT source FROM observation")
            ).scalars().all()

        assert "derived" not in sources


class TestClientNeverLeaksTheToken:
    def test_a_401_is_reported_as_an_expired_token(self):
        def handler(request):
            assert request.headers["Authorization"] == f"Bearer {TOKEN}"
            return httpx.Response(
                401, json={"detail": "Invalid token: Signature has expired"}
            )

        client = BodySpecClient()
        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as mocked:
            original = httpx.get
            httpx.get = lambda url, **kw: mocked.get(url, **kw)
            try:
                with pytest.raises(BodySpecAuthError, match="60 minutes"):
                    client.list_results(TOKEN)
            finally:
                httpx.get = original

    def test_other_errors_do_not_carry_the_request(self, caplog):
        """A 500 must not be reported by repr'ing the request, whose headers
        contain the bearer token."""

        def handler(request):
            return httpx.Response(500, json={"detail": "boom"})

        client = BodySpecClient()
        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as mocked:
            original = httpx.get
            httpx.get = lambda url, **kw: mocked.get(url, **kw)
            try:
                with caplog.at_level(logging.DEBUG):
                    with pytest.raises(BodySpecError) as raised:
                        client.list_results(TOKEN)
            finally:
                httpx.get = original

        assert TOKEN not in str(raised.value)
        assert TOKEN not in caplog.text

    def test_a_successful_sync_logs_nothing_containing_the_token(self, caplog):
        with caplog.at_level(logging.DEBUG):
            _sync(FakeClient())

        assert TOKEN not in caplog.text
