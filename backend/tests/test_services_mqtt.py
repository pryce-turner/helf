import json
import pytest

from app.services.mqtt_service import MQTTService

pytestmark = pytest.mark.usefixtures("db_engine")


def test_mqtt_on_message_creates_measurement():
    service = MQTTService()

    class StubRepo:
        def __init__(self):
            self.measurements = []

        def create(self, measurement):
            self.measurements.append(measurement)
            return {"doc_id": 1}

    stub_repo = StubRepo()
    service.body_comp_repo = stub_repo

    payload = {
        "date": "2024-01-01T12:00:00",
        "weight": 70.5,
        "fat": 18.2,
    }
    msg = type("Msg", (), {"topic": "openScaleSync/measurements/last", "payload": json.dumps(payload).encode()})

    service._on_message(None, None, msg)

    assert len(stub_repo.measurements) == 1
    measurement = stub_repo.measurements[0]
    assert measurement.weight == 70.5
    assert measurement.date == "2024-01-01"


def test_mqtt_on_message_skips_when_missing_fields():
    service = MQTTService()

    class StubRepo:
        def __init__(self):
            self.called = False

        def create(self, measurement):
            self.called = True
            return {"doc_id": 1}

    stub_repo = StubRepo()
    service.body_comp_repo = stub_repo

    payload = {"date": "2024-01-01T12:00:00"}
    msg = type("Msg", (), {"topic": "openScaleSync/measurements/last", "payload": json.dumps(payload).encode()})

    service._on_message(None, None, msg)

    assert stub_repo.called is False
