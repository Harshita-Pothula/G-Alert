"""Focused Flask API tests for Phase 2 sensor telemetry integration."""

import unittest
from datetime import datetime, timezone

import app as app_module
from sensor_telemetry import SensorTelemetryService


class SensorTelemetryApiTests(unittest.TestCase):
    def setUp(self):
        app_module.sensor_telemetry_service = SensorTelemetryService()
        self.client = app_module.app.test_client()
        self.payload = {
            "sensor_id": "VIB-API-001",
            "region_key": "Tsho_Rolpa_Nepal",
            "sensor_type": "vibration",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "reading": {"value": 2.4, "unit": "cm/s"},
            "sequence": 1,
        }

    def test_valid_post_telemetry(self):
        response = self.client.post("/api/sensors/telemetry", json=self.payload)
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["ingestion_status"], "ACCEPTED")

    def test_invalid_payload(self):
        response = self.client.post(
            "/api/sensors/telemetry",
            json={"sensor_id": "VIB-API-001"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()["status"], "error")

    def test_malformed_non_json_request(self):
        response = self.client.post(
            "/api/sensors/telemetry",
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["status"], "error")

    def test_duplicate_telemetry(self):
        first = self.client.post("/api/sensors/telemetry", json=self.payload)
        second = self.client.post("/api/sensors/telemetry", json=self.payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.get_json()["ingestion_status"], "DUPLICATE")

    def test_get_sensor_status(self):
        self.client.post("/api/sensors/telemetry", json=self.payload)
        response = self.client.get("/api/sensors/status/Tsho_Rolpa_Nepal")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        network = body["sensor_network_status"]
        self.assertEqual(body["data_source"], "SENSOR_TELEMETRY")
        self.assertEqual(network["sensors_deployed"], 1)
        self.assertEqual(network["sensors"][0]["status"], "ONLINE")

    def test_existing_endpoints_remain_available(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/regions").status_code, 200)


if __name__ == "__main__":
    unittest.main()
