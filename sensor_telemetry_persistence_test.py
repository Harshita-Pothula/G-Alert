"""Focused Phase 3 persistence tests for sensor telemetry."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app as app_module
from observation_store import ObservationStore
from sensor_telemetry import SensorTelemetryService


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def make_payload(sensor_id="VIB-PERSIST-001", timestamp=None, sequence=1, **extra):
    payload = {
        "sensor_id": sensor_id,
        "region_key": "Tsho_Rolpa_Nepal",
        "sensor_type": "vibration",
        "timestamp": (timestamp or NOW).isoformat().replace("+00:00", "Z"),
        "reading": {"value": 2.4, "unit": "cm/s"},
        "sequence": sequence,
    }
    payload.update(extra)
    return payload


class SensorTelemetryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.directory.name, "observations.sqlite3")
        self.database = patch.dict(
            os.environ, {"G_ALERT_OBSERVATIONS_DB": self.database_path}
        )
        self.database.start()
        app_module.sensor_telemetry_service = SensorTelemetryService()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.database.stop()
        self.directory.cleanup()

    def post(self, payload):
        return self.client.post("/api/sensors/telemetry", json=payload)

    def test_accepted_telemetry_is_persisted(self):
        response = self.post(
            make_payload(simulated=True, provenance={"source": "test-device"})
        )
        self.assertEqual(response.status_code, 200)
        reading = ObservationStore().get_latest_sensor_reading("VIB-PERSIST-001")
        self.assertIsNotNone(reading)
        self.assertEqual(reading["region_key"], "Tsho_Rolpa_Nepal")
        self.assertEqual(reading["reading"]["value"], 2.4)
        self.assertEqual(reading["sequence"], 1)
        self.assertEqual(reading["freshness"], "FRESH")
        self.assertTrue(reading["simulated"])
        self.assertEqual(reading["provenance"]["source"], "test-device")

    def test_invalid_telemetry_is_not_persisted(self):
        invalid = make_payload()
        del invalid["reading"]
        response = self.post(invalid)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(ObservationStore().list_sensor_telemetry("Tsho_Rolpa_Nepal"), [])

    def test_duplicate_telemetry_does_not_create_duplicate_record(self):
        payload = make_payload()
        self.assertEqual(self.post(payload).status_code, 200)

        app_module.sensor_telemetry_service = SensorTelemetryService()
        duplicate = self.post(payload)
        self.assertEqual(duplicate.status_code, 409)
        readings = ObservationStore().list_sensor_telemetry("Tsho_Rolpa_Nepal")
        self.assertEqual(len(readings), 1)

    def test_hash_duplicate_ignores_optional_provenance_metadata(self):
        payload = make_payload(sequence=None, simulated=True)
        self.assertEqual(self.post(payload).status_code, 200)

        app_module.sensor_telemetry_service = SensorTelemetryService()
        retry = make_payload(sequence=None)
        self.assertEqual(self.post(retry).status_code, 409)
        readings = ObservationStore().list_sensor_telemetry("Tsho_Rolpa_Nepal")
        self.assertEqual(len(readings), 1)

    def test_latest_sensor_reading_can_be_retrieved(self):
        self.assertEqual(
            self.post(make_payload(timestamp=NOW - timedelta(minutes=2), sequence=1)).status_code,
            200,
        )
        self.assertEqual(
            self.post(
                make_payload(
                    timestamp=NOW - timedelta(minutes=1),
                    sequence=2,
                    reading={"value": 3.1, "unit": "cm/s"},
                )
            ).status_code,
            200,
        )
        response = self.client.get("/api/sensors/telemetry/VIB-PERSIST-001/latest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["reading"]["reading"]["value"], 3.1)

    def test_region_sensor_history_can_be_retrieved(self):
        self.assertEqual(
            self.post(make_payload(sensor_id="VIB-PERSIST-001", sequence=1)).status_code,
            200,
        )
        self.assertEqual(
            self.post(make_payload(sensor_id="VIB-PERSIST-002", sequence=2)).status_code,
            200,
        )
        response = self.client.get(
            "/api/sensors/telemetry/Tsho_Rolpa_Nepal/history?limit=10"
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["readings"]), 2)


if __name__ == "__main__":
    unittest.main()
