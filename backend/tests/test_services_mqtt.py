import json

import pytest

from app.services.mqtt_service import KG_TO_LB, MQTTService

pytestmark = pytest.mark.usefixtures("db_engine")


class StubRepo:
    def __init__(self):
        self.measurements = []
        self.sources = []

    def create(self, measurement, source="manual"):
        self.measurements.append(measurement)
        self.sources.append(source)
        return {"doc_id": 1}


def _deliver(payload, repo=None):
    """Push one openScale payload through _on_message, return what was stored."""
    service = MQTTService()
    stub_repo = repo or StubRepo()
    service.body_comp_repo = stub_repo

    msg = type(
        "Msg",
        (),
        {
            "topic": "openScaleSync/measurements/last",
            "payload": json.dumps(payload).encode(),
        },
    )
    service._on_message(None, None, msg)
    return stub_repo.measurements


def test_mqtt_tags_readings_as_openscale():
    """The mirrored metric rows must continue the backfilled series.

    A different source string would fork eight months of history into two
    incomparable ones.
    """
    repo = StubRepo()
    _deliver({"date": "2024-01-01T12:00:00", "weight": 70.5}, repo=repo)

    assert repo.sources == ["openscale"]


def test_mqtt_on_message_creates_measurement():
    measurements = _deliver(
        {"date": "2024-01-01T12:00:00", "weight": 70.5, "fat": 18.2}
    )

    assert len(measurements) == 1
    assert measurements[0].date == "2024-01-01"


def test_mqtt_converts_weight_to_pounds():
    """openScale reports kg; pounds are canonical (ADR-0003)."""
    measurements = _deliver({"date": "2024-01-01T12:00:00", "weight": 70.5})

    assert measurements[0].weight == pytest.approx(70.5 * KG_TO_LB)
    assert measurements[0].weight == pytest.approx(155.4, abs=0.1)
    assert measurements[0].weight_unit == "lbs"


def test_mqtt_does_not_convert_percentages():
    """The asymmetry that makes this easy to get wrong.

    `muscle` is a percentage despite the column being named muscle_mass, so it
    must pass through untouched while `weight` is scaled. Converting it is the
    bug that rendered 39.1% as "86.2 lbs" on the frontend for months.
    """
    measurements = _deliver(
        {
            "date": "2024-01-01T12:00:00",
            "weight": 70.5,
            "fat": 18.2,
            "muscle": 39.1,
            "water": 55.0,
            "protein": 17.5,
        }
    )

    stored = measurements[0]
    assert stored.muscle_mass == 39.1
    assert stored.body_fat_pct == 18.2
    assert stored.water_pct == 55.0
    assert stored.protein_pct == 17.5


def test_mqtt_stores_bone_mass_in_kilograms_unconverted():
    """Bone is a genuine mass, but it is *not* converted (Plan 0010 §2).

    `metric_def` already defines `bone_mass_kg` for DEXA and openScale reports
    kg; a pounds copy would put one quantity under two names, which is what
    ADR-0003's naming rule exists to prevent. Only `weight` converts.
    """
    measurements = _deliver(
        {"date": "2024-01-01T12:00:00", "weight": 70.5, "bone": 3.2}
    )

    assert measurements[0].bone_mass_kg == pytest.approx(3.2)
    assert measurements[0].weight == pytest.approx(70.5 * KG_TO_LB)


def test_mqtt_leaves_absent_bone_mass_as_none():
    measurements = _deliver({"date": "2024-01-01T12:00:00", "weight": 70.5})

    assert measurements[0].bone_mass_kg is None


def test_mqtt_on_message_skips_when_missing_fields():
    assert _deliver({"date": "2024-01-01T12:00:00"}) == []
