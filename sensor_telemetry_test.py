"""Deterministic Phase 1 tests for sensor_telemetry."""

import unittest
from datetime import datetime, timedelta, timezone

from sensor_telemetry import (
    HEALTH_INVALID,
    HEALTH_ONLINE,
    HEALTH_STALE,
    HEALTH_UNKNOWN,
    SensorTelemetryService,
)


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def payload(**overrides):
    value = {
        "sensor_id": "VIB-001",
        "region_key": "Tsho_Rolpa_Nepal",
        "sensor_type": "vibration",
        "timestamp": "2026-09-06T11:59:00Z",
        "reading": {"value": 2.4, "unit": "cm/s"},
    }
    value.update(overrides)
    return value


class SensorTelemetryServiceTests(unittest.TestCase):
    def test_valid_reading(self):
        result = SensorTelemetryService().ingest(payload(), now=NOW)
        self.assertEqual(result["ingestion_status"], "ACCEPTED")
        self.assertEqual(result["freshness"], "FRESH")
        self.assertEqual(result["sensor_status"], HEALTH_ONLINE)

    def test_missing_required_field(self):
        data = payload()
        del data["reading"]
        result = SensorTelemetryService().ingest(data, now=NOW)
        self.assertEqual(result["ingestion_status"], "REJECTED")
        self.assertIn("missing required field: reading", result["errors"])

    def test_invalid_sensor_type(self):
        result = SensorTelemetryService().ingest(
            payload(sensor_type="temperature"), now=NOW
        )
        self.assertEqual(result["sensor_status"], HEALTH_INVALID)
        self.assertTrue(any("unsupported sensor_type" in error for error in result["errors"]))

    def test_invalid_region(self):
        result = SensorTelemetryService().ingest(
            payload(region_key="Unknown_Region"), now=NOW
        )
        self.assertEqual(result["ingestion_status"], "REJECTED")
        self.assertTrue(any("Unknown or invalid region" in error for error in result["errors"]))

    def test_invalid_timestamp(self):
        result = SensorTelemetryService().ingest(
            payload(timestamp="not-a-timestamp"), now=NOW
        )
        self.assertEqual(result["ingestion_status"], "REJECTED")
        self.assertIn("timestamp must be a timezone-aware ISO-8601 UTC timestamp", result["errors"])

    def test_duplicate_reading_with_sequence(self):
        service = SensorTelemetryService()
        data = payload(sequence=7)
        first = service.ingest(data, now=NOW)
        second = service.ingest(data, now=NOW)
        self.assertEqual(first["ingestion_status"], "ACCEPTED")
        self.assertEqual(second["ingestion_status"], "DUPLICATE")
        self.assertTrue(second["duplicate"])

    def test_duplicate_reading_uses_hash_without_sequence(self):
        service = SensorTelemetryService()
        first = service.ingest(payload(), now=NOW)
        second = service.ingest(payload(), now=NOW)
        self.assertEqual(first["ingestion_status"], "ACCEPTED")
        self.assertEqual(second["ingestion_status"], "DUPLICATE")

    def test_stale_reading(self):
        service = SensorTelemetryService(stale_after_seconds=300)
        result = service.ingest(
            payload(timestamp="2026-09-06T11:50:00Z"), now=NOW
        )
        self.assertEqual(result["freshness"], "STALE")
        self.assertEqual(result["sensor_status"], HEALTH_STALE)

    def test_fresh_reading(self):
        service = SensorTelemetryService(stale_after_seconds=300)
        result = service.ingest(
            payload(timestamp="2026-09-06T11:58:00Z"), now=NOW
        )
        self.assertEqual(result["freshness"], "FRESH")
        self.assertEqual(result["sensor_status"], HEALTH_ONLINE)

    def test_sensor_health_status(self):
        service = SensorTelemetryService(stale_after_seconds=300)
        self.assertEqual(service.get_sensor_status("VIB-UNKNOWN")["status"], HEALTH_UNKNOWN)

        service.ingest(payload(), now=NOW)
        self.assertEqual(service.get_sensor_status("VIB-001", now=NOW)["status"], HEALTH_ONLINE)
        self.assertEqual(
            service.get_sensor_status("VIB-001", now=NOW + timedelta(minutes=6))["status"],
            HEALTH_STALE,
        )

        invalid = payload(sensor_id="VIB-BAD", reading={"value": -1, "unit": "cm/s"})
        service.ingest(invalid, now=NOW)
        self.assertEqual(service.get_sensor_status("VIB-BAD")["status"], HEALTH_INVALID)


if __name__ == "__main__":
    unittest.main()
