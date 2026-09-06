"""Production API integration tests for the seven-stage monitoring manager."""

from unittest.mock import patch

from app import app
from execution_manager import STAGE_ORDER


def _observation(quality_status="APPLIED", status="SUCCESS"):
    return {
        "status": status,
        "region": "Tsho_Rolpa_Nepal",
        "validity_status": "VALID" if status == "SUCCESS" else "UNAVAILABLE",
        "provenance": {"type": "DERIVED_FROM_REAL_DATA", "source": "test"},
        "satellite": {
            "status": status,
            "image_id": "sentinel-test-image",
            "acquisition_time": "2026-09-04T05:00:00+00:00",
            "quality_masking": {"status": quality_status},
            "data_quality": {"confidence": 0.9, "valid_pixel_fraction": 0.9},
            "candidate_detection": {"identity_status": "IDENTITY_SUPPORTED"},
            "seasonal_comparison": {
                "status": "VALID",
                "baseline": {"statistics": {"mean": 10.0}},
                "baseline_value": 10.0,
                "current_value": 10.0,
                "deviation_percentage": 0.0,
            },
            "water_area": {"status": "SUCCESS", "area_sqkm": 10.0},
        },
        "decision_support": {"status": "PROTOTYPE_ASSESSMENT", "risk_available": True},
        "risk": {
            "risk_level": "SAFE",
            "assessment_status": "COMPLETE",
            "decision_support_status": "MULTI_SIGNAL",
            "confidence": "PROTOTYPE_LIMITED",
            "unavailable_information": [],
            "simulated_signals": [],
            "assumptions": [],
            "explanation": "test evidence",
        },
    }


class _Store:
    saves = 0

    def save(self, *_args):
        _ = _args
        self.saves += 1
        return {
            "observation_id": "stored-test-observation",
            "recorded_at": "2026-09-05T00:00:00+00:00",
        }


def test_api_monitor_invokes_manager_and_runs_all_stages_in_order():
    store = _Store()
    calls = []

    from main import MonitoringExecutionManager as RealManager

    class SpyManager(RealManager):
        def run(self, initial_context=None):
            result = super().run(initial_context)
            calls.extend(result["completed_stages"])
            return result

    client = app.test_client()
    with patch("main._run_integrated_monitoring", return_value=_observation()), patch(
        "main.ObservationStore", return_value=store
    ), patch("main.MonitoringExecutionManager", SpyManager):
        response = client.get("/api/monitor/Tsho_Rolpa_Nepal")

    body = response.get_json()
    assert response.status_code == 200
    assert calls == list(STAGE_ORDER)
    assert body["execution"]["job_status"] == "SUCCEEDED"
    assert body["execution"]["completed_stages"] == list(STAGE_ORDER)
    assert body["early_warning_status"]["status"] == "NORMAL"
    assert store.saves == 1


def test_api_monitor_propagates_quality_failure_and_skips_downstream():
    store = _Store()
    client = app.test_client()
    with patch(
        "main._run_integrated_monitoring",
        return_value=_observation(quality_status="MASKING_FAILED"),
    ), patch("main.ObservationStore", return_value=store):
        response = client.get("/api/monitor/Tsho_Rolpa_Nepal")

    body = response.get_json()
    assert response.status_code == 200
    assert body["execution"]["job_status"] == "FAILED"
    assert body["execution"]["failed_stage"] == "DATA_QUALITY_MASKING"
    assert body["execution"]["skipped_stages"] == list(STAGE_ORDER[2:])
    assert body["execution"]["system_status"] == "INSUFFICIENT_DATA"
    assert body["status"] == "ERROR"
    assert body["validity_status"] == "UNAVAILABLE"
    assert store.saves == 0


def test_api_monitor_preserves_insufficient_data_status():
    store = _Store()
    observation = _observation()
    observation["satellite"]["seasonal_comparison"] = {
        "status": "INSUFFICIENT_HISTORICAL_DATA"
    }
    client = app.test_client()
    with patch("main._run_integrated_monitoring", return_value=observation), patch(
        "main.ObservationStore", return_value=store
    ):
        response = client.get("/api/monitor/Tsho_Rolpa_Nepal")

    body = response.get_json()
    assert response.status_code == 200
    assert body["execution"]["failed_stage"] == "SEASONAL_BASELINE_COMPARISON"
    assert body["status"] == "INSUFFICIENT_DATA"
    assert body["validity_status"] == "UNAVAILABLE"
    assert store.saves == 1


def test_api_monitor_completes_with_limited_risk_confidence():
    store = _Store()
    observation = _observation()
    observation["risk"] = {
        "risk_level": "UNKNOWN",
        "assessment_status": "LIMITED_CONFIDENCE",
        "decision_support_status": "LIMITED_DATA",
        "confidence": "LIMITED",
        "unavailable_information": ["sensor signal was not supplied"],
        "missing_inputs": ["sensor"],
        "simulated_signals": [],
        "assumptions": [],
        "explanation": "No complete evidence basis is available for a definitive risk level.",
    }
    client = app.test_client()
    with patch("main._run_integrated_monitoring", return_value=observation), patch(
        "main.ObservationStore", return_value=store
    ):
        response = client.get("/api/monitor/Imja_Tsho_Nepal")

    body = response.get_json()
    assert response.status_code == 200
    assert body["execution"]["job_status"] == "SUCCEEDED"
    assert body["execution"]["failed_stage"] is None
    assert body["execution"]["system_status"] == "INSUFFICIENT_DATA"
    assert body["risk"]["risk_level"] == "UNKNOWN"
    assert body["risk"]["assessment_status"] == "LIMITED_CONFIDENCE"
    assert store.saves == 1


if __name__ == "__main__":
    test_api_monitor_invokes_manager_and_runs_all_stages_in_order()
    test_api_monitor_propagates_quality_failure_and_skips_downstream()
    print("Production execution integration tests: PASS")