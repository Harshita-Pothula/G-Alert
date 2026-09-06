"""Focused reliability tests for active GEE acquisition and processing."""

from gee_reliability import GEEReliabilityLayer, merge_reliability_metadata, unavailable_observation
from early_warning_status import evaluate_early_warning_status


def test_timeout_becomes_unavailable_and_cannot_be_valid_evidence():
    layer = GEEReliabilityLayer()
    result = layer.execute(
        lambda: (_ for _ in ()).throw(TimeoutError("GEE request timed out")),
        stage="IMAGERY_ACQUISITION",
    )
    assert result["ok"] is False
    assert result["status"] == "UNAVAILABLE"
    assert result["validity_status"] == "UNAVAILABLE"
    assert result["error_category"] == "TIMEOUT"

    observation = unavailable_observation("Tsho_Rolpa_Nepal", result["reason"])
    assert observation["validity_status"] == "UNAVAILABLE"
    assert observation["satellite"]["status"] == "UNAVAILABLE"
    assert observation["decision_support"]["risk_available"] is False
    assert evaluate_early_warning_status(observation)["status"] == "INSUFFICIENT_DATA"


def test_empty_or_partial_result_is_unavailable():
    layer = GEEReliabilityLayer()
    result = layer.execute(
        lambda: (None, {"attempts": []}),
        stage="IMAGERY_ACQUISITION",
        validator=lambda value: value[0] is not None,
    )
    assert result["status"] == "UNAVAILABLE"
    assert result["error_category"] == "EMPTY_OR_UNUSABLE_RESULT"


def test_processing_failure_marks_existing_envelope_unavailable():
    layer = GEEReliabilityLayer()
    failure = layer.failure("NDWI_PROCESSING", RuntimeError("server service error"))
    existing = {
        "status": "SUCCESS",
        "satellite": {"status": "SUCCESS", "water_area": {"area_sqkm": 1.2}},
        "decision_support": {"status": "PROTOTYPE_ASSESSMENT", "risk_available": True},
    }
    result = merge_reliability_metadata(existing, failure)
    assert result["validity_status"] == "UNAVAILABLE"
    assert result["satellite"]["status"] == "UNAVAILABLE"
    assert result["satellite"].get("water_area") == {"area_sqkm": 1.2}
    assert result["decision_support"]["risk_available"] is False


if __name__ == "__main__":
    test_timeout_becomes_unavailable_and_cannot_be_valid_evidence()
    test_empty_or_partial_result_is_unavailable()
    test_processing_failure_marks_existing_envelope_unavailable()
    print("GEE reliability tests: PASS")