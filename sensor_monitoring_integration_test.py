"""Focused Phase 4 tests for persisted telemetry selection in monitoring."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import main
from observation_store import ObservationStore
from risk_engine import RiskEngine
from sensor_telemetry import SensorTelemetryService


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def telemetry_payload(sensor_id, sensor_type, value, unit, timestamp, sequence=None, simulated=None):
    payload = {
        "sensor_id": sensor_id,
        "region_key": "Tsho_Rolpa_Nepal",
        "sensor_type": sensor_type,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "reading": {"value": value, "unit": unit},
    }
    if sequence is not None:
        payload["sequence"] = sequence
    if simulated is not None:
        payload["simulated"] = simulated
    return payload


class SensorMonitoringIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.directory.name, "observations.sqlite3")
        self.environment = patch.dict(
            os.environ, {"G_ALERT_OBSERVATIONS_DB": self.database_path}
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def persist(self, payload):
        service = SensorTelemetryService()
        result = service.ingest(payload, now=NOW)
        self.assertEqual(result["ingestion_status"], "ACCEPTED")
        ObservationStore().save_sensor_telemetry(result, source_payload=payload)

    def test_latest_fresh_readings_are_selected_and_labeled(self):
        self.persist(
            telemetry_payload(
                "VIB-001", "vibration", 18.2, "cm/s", NOW - timedelta(minutes=2), 1
            )
        )
        self.persist(
            telemetry_payload(
                "WATER-001", "water_level", 1.82, "m", NOW - timedelta(minutes=1), 2,
                simulated=True,
            )
        )

        evidence = main._load_persisted_sensor_evidence("Tsho_Rolpa_Nepal", now=NOW)

        self.assertEqual(evidence["status"], "PERSISTED_TELEMETRY")
        self.assertEqual(evidence["freshness"], "FRESH")
        self.assertEqual(set(evidence["sensor_ids"]), {"VIB-001", "WATER-001"})
        self.assertTrue(evidence["simulated"])
        self.assertEqual(evidence["risk_inputs"]["vibration_cmps"], 18.2)
        self.assertEqual(evidence["risk_inputs"]["water_level_cm"], 182.0)
        self.assertEqual(len(evidence["readings"]), 2)

    def test_stale_readings_are_not_risk_inputs(self):
        self.persist(
            telemetry_payload(
                "VIB-STALE", "vibration", 30.0, "cm/s", NOW - timedelta(minutes=10), 1
            )
        )

        evidence = main._load_persisted_sensor_evidence("Tsho_Rolpa_Nepal", now=NOW)

        self.assertEqual(evidence["status"], "STALE_TELEMETRY")
        self.assertEqual(evidence["freshness"], "STALE")
        self.assertEqual(evidence["readings"], [])
        self.assertEqual(evidence["risk_inputs"], {})
        self.assertFalse(evidence["usable_for_risk"])

    def test_missing_telemetry_is_explicit(self):
        evidence = main._load_persisted_sensor_evidence("Tsho_Rolpa_Nepal", now=NOW)
        self.assertEqual(evidence["status"], "NO_PERSISTED_TELEMETRY")
        self.assertFalse(evidence["has_records"])
        self.assertFalse(evidence["simulated"])
        self.assertEqual(evidence["sensor_ids"], [])

    def test_fresh_inputs_use_existing_risk_calculation(self):
        self.persist(
            telemetry_payload(
                "VIB-001", "vibration", 18.2, "cm/s", NOW - timedelta(minutes=1), 1
            )
        )
        evidence = main._load_persisted_sensor_evidence("Tsho_Rolpa_Nepal", now=NOW)
        signal = RiskEngine().calculate_sensor_signal(evidence["risk_inputs"])
        self.assertEqual(signal, 0.3)


if __name__ == "__main__":
    unittest.main()
