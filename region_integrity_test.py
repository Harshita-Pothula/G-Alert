"""Focused cross-region isolation tests."""

import os
import tempfile
from unittest.mock import patch

from alert_event_lifecycle import AlertCreationRejected, AlertEventLifecycleManager
from downstream_impact import build_downstream_impact
from impact_mapping import build_impact_mapping
from early_warning_status import build_human_warning
from main import (
    _data_confidence_summary,
    _integrated_result_skeleton,
    _risk_change_explanation,
    _validate_nested_region_identity,
    run_integrated_monitoring,
)
from observation_store import ObservationStore


def _observation(region, area, score=0.2):
    return {
        "status": "SUCCESS",
        "validity_status": "VALID",
        "region": region,
        "satellite": {
            "status": "SUCCESS",
            "region": region,
            "image_id": f"image-{region}",
            "acquisition_time": "2026-09-05T05:00:00+00:00",
            "water_area": {"status": "SUCCESS", "area_sqkm": area},
        },
        "risk": {
            "risk_score": score,
            "risk_level": "SAFE",
            "assessment_status": "COMPLETE",
        },
        "observed_measurement": {
            "status": "UNAVAILABLE",
            "area_sqkm": None,
        },
    }


def _assessment():
    return {
        "region": "Tsho_Rolpa_Nepal",
        "risk_level": "WARNING",
        "assessment_status": "COMPLETE",
        "observed_evidence": ["verified evidence"],
        "simulated_signals": [],
        "unavailable_information": [],
    }


def test_observations_and_previous_values_are_region_isolated():
    with tempfile.TemporaryDirectory() as directory:
        store = ObservationStore(os.path.join(directory, "observations.sqlite3"))
        tsho = _observation("Tsho_Rolpa_Nepal", 10.0)
        imja = _observation("Imja_Tsho_Nepal", 20.0)
        store.save(tsho)
        store.save(imja)
        assert [item["region"] for item in store.list("Tsho_Rolpa_Nepal")] == ["Tsho_Rolpa_Nepal"]
        assert [item["region"] for item in store.list("Imja_Tsho_Nepal")] == ["Imja_Tsho_Nepal"]
        assert store.get_previous_valid_observation("Tsho_Rolpa_Nepal")["observation"]["satellite"]["water_area"]["area_sqkm"] == 10.0
        assert store.get_previous_valid_observation("Imja_Tsho_Nepal")["observation"]["satellite"]["water_area"]["area_sqkm"] == 20.0


def test_storage_and_alerts_reject_invalid_or_mismatched_regions():
    with tempfile.TemporaryDirectory() as directory:
        store = ObservationStore(os.path.join(directory, "observations.sqlite3"))
        invalid = _observation("Tsho_Rolpa_Nepal", 10.0)
        invalid["satellite"]["region"] = "Imja_Tsho_Nepal"
        try:
            store.save(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("mismatched satellite region was persisted")

        manager = AlertEventLifecycleManager(os.path.join(directory, "alerts.sqlite3"))
        evidence = {"region": "Imja_Tsho_Nepal", "provenance": {"type": "REAL_SATELLITE_DATA"}}
        try:
            manager.create_alert(
                _assessment(),
                evidence,
                region="Tsho_Rolpa_Nepal",
                provenance=evidence["provenance"],
            )
        except AlertCreationRejected:
            pass
        else:
            raise AssertionError("mismatched alert snapshot was accepted")


def test_monitoring_rejects_mismatched_internal_result():
    wrong_region = _observation("Imja_Tsho_Nepal", 20.0)
    with patch("main._run_integrated_monitoring", return_value=wrong_region):
        result = run_integrated_monitoring("Tsho_Rolpa_Nepal")
    assert result["status"] == "ERROR"
    assert "region" in result["reason"].lower()


def test_downstream_context_mismatch_is_rejected():
    context = {"region_key": "Imja_Tsho_Nepal", "status": "COMMUNITY_DATA"}
    try:
        build_downstream_impact("Tsho_Rolpa_Nepal", {}, context)
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched downstream context was accepted")
    try:
        build_impact_mapping("Tsho_Rolpa_Nepal", {}, context)
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched impact context was accepted")


def test_nested_response_sections_carry_selected_region():
    with tempfile.TemporaryDirectory() as directory:
        for region in ("Tsho_Rolpa_Nepal", "Imja_Tsho_Nepal"):
            observation = _integrated_result_skeleton(region, "SUCCESS")
            observation["risk"] = {
                "risk_score": 0.1,
                "risk_level": "SAFE",
                "assessment_status": "COMPLETE",
            }
            observation["data_confidence"] = _data_confidence_summary(observation)
            observation["human_warning"] = build_human_warning(observation)
            observation["risk_change_explanation"] = _risk_change_explanation(
                ObservationStore(os.path.join(directory, f"{region}.sqlite3")),
                region,
                observation,
            )
            _validate_nested_region_identity(observation, region)
            for section_name in (
                "weather",
                "human_warning",
                "data_confidence",
                "alert_confirmation",
                "satellite_change",
                "risk_change_explanation",
                "satellite_change_evidence",
            ):
                assert observation[section_name]["region"] == region


if __name__ == "__main__":
    test_observations_and_previous_values_are_region_isolated()
    test_storage_and_alerts_reject_invalid_or_mismatched_regions()
    test_monitoring_rejects_mismatched_internal_result()
    test_downstream_context_mismatch_is_rejected()
    print("Region integrity tests: PASS")
