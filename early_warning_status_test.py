"""Focused tests for the coherent early-warning status model."""

from copy import deepcopy

from early_warning_status import (
    INSUFFICIENT_DATA,
    NORMAL,
    UNCONFIRMED,
    WARNING,
    WATCH,
    build_human_warning,
    evaluate_early_warning_status,
)


def _observation(risk_level="SAFE"):
    return {
        "status": "SUCCESS",
        "region": "Tsho_Rolpa_Nepal",
        "provenance": {
            "type": "DERIVED_FROM_REAL_DATA",
            "source": "Google Earth Engine Sentinel-2 and verified sensors",
            "limitations": ["Prototype evidence model"],
        },
        "satellite": {
            "status": "SUCCESS",
            "image_id": "sentinel-image-123",
            "acquisition_time": "2026-09-04T05:00:00+00:00",
            "quality_masking": {"status": "APPLIED"},
            "data_quality": {"confidence": 0.9},
            "candidate_detection": {"identity_status": "IDENTITY_SUPPORTED"},
        },
        "temporal_evidence": {
            "status": "TEMPORAL_IDENTITY_SUPPORTING",
            "identity_status": "IDENTITY_SUPPORTED",
        },
        "decision_support": {"status": "PROTOTYPE_ASSESSMENT", "risk_available": True},
        "risk": {
            "risk_level": risk_level,
            "assessment_status": "COMPLETE",
            "confidence": "PROTOTYPE_LIMITED",
            "risk_score": 0.1 if risk_level == "SAFE" else 0.42,
            "explanation": "Structured risk explanation",
            "assumptions": ["Prototype thresholds"],
            "unavailable_information": [],
            "simulated_signals": [],
        },
    }


def test_valid_normal_condition():
    result = evaluate_early_warning_status(_observation("SAFE"))
    assert result["status"] == NORMAL


def test_developing_condition_is_watch():
    result = evaluate_early_warning_status(_observation("WARNING"))
    assert result["status"] == WATCH


def test_verified_high_risk_condition_is_warning():
    result = evaluate_early_warning_status(_observation("HIGH_RISK"))
    assert result["status"] == WARNING


def test_ambiguous_identity_is_unconfirmed():
    observation = _observation("HIGH_RISK")
    observation["temporal_evidence"]["status"] = "TEMPORAL_IDENTITY_AMBIGUOUS"
    observation["temporal_evidence"]["identity_status"] = "IDENTITY_AMBIGUOUS"
    result = evaluate_early_warning_status(observation)
    assert result["status"] == UNCONFIRMED
    assert result["status"] != WARNING


def test_stale_data_is_insufficient():
    observation = _observation("HIGH_RISK")
    observation["status"] = "STALE_IMAGERY"
    observation["satellite"]["status"] = "STALE_IMAGERY"
    result = evaluate_early_warning_status(observation)
    assert result["status"] == INSUFFICIENT_DATA


def test_missing_evidence_never_becomes_normal():
    observation = _observation("SAFE")
    observation.pop("risk")
    result = evaluate_early_warning_status(observation)
    assert result["status"] == INSUFFICIENT_DATA
    assert result["status"] != NORMAL


def test_provenance_and_explanation_are_preserved():
    observation = _observation("WARNING")
    original = deepcopy(observation)
    result = evaluate_early_warning_status(observation)
    assert result["provenance"] == original["provenance"]
    assert result["explanation"]["risk_explanation"] == "Structured risk explanation"
    assert result["explanation"]["assumptions"] == ["Prototype thresholds"]
    assert result["evidence_state"]["identity_status"] == "IDENTITY_SUPPORTED"


def test_human_warning_separates_status_evidence_and_action_from_risk_score():
    observation = _observation("HIGH_RISK")
    observation["satellite"]["seasonal_comparison"] = {"status": "VALID"}
    observation["satellite_change"] = {
        "current_area_sqkm": 12.0,
        "previous_area_sqkm": 10.0,
        "previous_observation_percent_change": 20.0,
        "trend": "INCREASING",
    }
    observation["data_confidence"] = {"level": "MEDIUM"}
    status_result = evaluate_early_warning_status(observation)
    warning = build_human_warning(observation, status_result)
    assert warning["status"] == WARNING
    assert warning["level"] == "WARNING"
    assert warning["reasons"]
    assert warning["supporting_evidence"]
    assert any("20.0%" in item for item in warning["supporting_evidence"])
    assert warning["recommended_action"]
    assert warning["technical_details_separate"] is True
    assert "risk_score" not in warning


if __name__ == "__main__":
    test_valid_normal_condition()
    test_developing_condition_is_watch()
    test_verified_high_risk_condition_is_warning()
    test_ambiguous_identity_is_unconfirmed()
    test_stale_data_is_insufficient()
    test_missing_evidence_never_becomes_normal()
    test_provenance_and_explanation_are_preserved()
    test_human_warning_separates_status_evidence_and_action_from_risk_score()
    print("Early-warning status tests: PASS")