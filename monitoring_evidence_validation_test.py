"""Focused tests for evidence cross-validation and final status persistence."""

import os
import tempfile
import unittest
from unittest.mock import patch

import main
from observation_store import ObservationStore


class MonitoringEvidenceValidationTests(unittest.TestCase):
    def test_real_evidence_cross_validation_reports_consistency(self):
        observation = {
            "region": "Tsho_Rolpa_Nepal",
            "satellite": {
                "acquisition_time": "2026-09-06T10:00:00+00:00",
                "provenance": {"type": "REAL_SATELLITE_DATA", "source": "Sentinel-2"},
            },
            "satellite_change_evidence": {
                "status": "CHANGE_EVIDENCE_ESTABLISHED",
                "change_magnitude": {
                    "water_area_status": "EXPANSION_RELATIVE_TO_SEASONAL_BASELINE",
                    "water_area_deviation_percentage": 25.0,
                },
            },
            "weather": {
                "status": "SUCCESS",
                "rainfall_mmph": 20.0,
                "observation_time": "2026-09-06T10:05:00+00:00",
                "provenance": {"type": "REAL_WEATHER_DATA", "source": "Open-Meteo"},
            },
        }
        sensors = {
            "readings": [{
                "sensor_id": "SENSOR-001",
                "timestamp": "2026-09-06T10:04:00+00:00",
                "provenance": {"type": "REAL_SENSOR_DATA", "source": "device"},
            }]
        }
        result = main._build_cross_validation(observation, sensors, 0.3)
        self.assertEqual(result["status"], "CONSISTENT")
        self.assertEqual(result["checks"]["satellite_weather"]["status"], "CONSISTENT")
        self.assertEqual(result["checks"]["satellite_sensors"]["status"], "CONSISTENT")
        self.assertEqual(
            result["checks"]["satellite_weather"]["timestamps"]["weather"],
            "2026-09-06T10:05:00+00:00",
        )

    def test_missing_weather_and_sensors_are_not_claimed_as_agreement(self):
        observation = {
            "region": "Tsho_Rolpa_Nepal",
            "satellite": {"acquisition_time": "2026-09-06T10:00:00+00:00"},
            "satellite_change_evidence": {"status": "NOT_AVAILABLE"},
            "weather": {"status": "UNAVAILABLE"},
        }
        result = main._build_cross_validation(observation, None, None)
        self.assertEqual(result["status"], "NOT_AVAILABLE")
        self.assertEqual(result["checks"]["satellite_weather"]["status"], "NOT_AVAILABLE")
        self.assertEqual(result["checks"]["satellite_sensors"]["status"], "NOT_AVAILABLE")

    def test_execution_failure_updates_persisted_root_status(self):
        fixture = {
            "status": "SUCCESS",
            "validity_status": "VALID",
            "region": "Tsho_Rolpa_Nepal",
            "mode": "monitoring",
            "provenance": {"type": "DERIVED_FROM_REAL_DATA", "source": "fixture"},
            "satellite": {
                "status": "SUCCESS",
                "image_id": "image-1",
                "acquisition_time": "2026-09-06T10:00:00+00:00",
                "quality_masking": {"status": "APPLIED"},
                "data_quality": {"confidence": 0.9, "valid_pixel_fraction": 0.9},
                "seasonal_comparison": {
                    "status": "INSUFFICIENT_HISTORICAL_DATA",
                    "baseline": {"status": "INSUFFICIENT_HISTORICAL_DATA"},
                },
            },
            "decision_support": {"status": "PROTOTYPE_ASSESSMENT", "risk_available": True},
            "risk": {
                "assessment_status": "COMPLETE",
                "decision_support_status": "MULTI_SIGNAL",
                "unavailable_information": [],
                "missing_inputs": [],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "observations.sqlite3")
            with patch.dict(os.environ, {"G_ALERT_OBSERVATIONS_DB": database_path}):
                with patch("main._run_integrated_monitoring", return_value=fixture):
                    result = main.run_integrated_monitoring("Tsho_Rolpa_Nepal")
                stored = ObservationStore(database_path).list("Tsho_Rolpa_Nepal")[0]
            self.assertEqual(result["status"], "INSUFFICIENT_DATA")
            self.assertEqual(stored["status"], "INSUFFICIENT_DATA")
            self.assertEqual(stored["observation"]["status"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
