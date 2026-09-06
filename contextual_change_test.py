"""Focused tests for contextual satellite change evidence."""

from contextual_change import (
    CHANGE_EVIDENCE_ESTABLISHED,
    CHANGE_EVIDENCE_INSUFFICIENT,
    CHANGE_NOT_ESTABLISHED,
    evaluate_contextual_change,
)


BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[86.46, 27.85], [86.48, 27.85], [86.48, 27.87], [86.46, 27.87], [86.46, 27.85]]],
}


def _comparison(current=15.0, baseline=10.0):
    historical = [
        {"acquisition_time": "2022-05-10", "water_area_sqkm": 9.0, "status": "SUCCESS", "boundary": BOUNDARY},
        {"acquisition_time": "2023-05-10", "water_area_sqkm": 10.0, "status": "SUCCESS", "boundary": BOUNDARY},
        {"acquisition_time": "2024-05-10", "water_area_sqkm": 11.0, "status": "SUCCESS", "boundary": BOUNDARY},
    ]
    return {
        "status": "VALID",
        "current_value": current,
        "baseline_value": baseline,
        "deviation": current - baseline,
        "deviation_percentage": ((current - baseline) / baseline) * 100,
        "baseline": {
            "status": "VALID",
            "observations": historical,
            "statistics": {"mean": baseline},
            "provenance": {"type": "DERIVED_FROM_REAL_DATA"},
        },
        "provenance": {"type": "DERIVED_FROM_REAL_DATA"},
    }


def _current(cloud_cover=10):
    return {
        "water_area_sqkm": 15.0,
        "boundary": BOUNDARY,
        "identity_status": "IDENTITY_SUPPORTED",
        "cloud_cover_percent": cloud_cover,
        "quality_masking": {"status": "APPLIED"},
        "data_quality": {"confidence": 0.9, "valid_pixel_fraction": 0.9},
        "provenance": {"type": "DERIVED_FROM_REAL_DATA"},
    }


def _temporal():
    return {
        "identity_status": "IDENTITY_SUPPORTED",
        "minimum_observations": 3,
        "usable_observation_ids": ["a", "b", "c"],
        "tracks": [{"observation_count": 3}],
    }


def test_meaningful_change_uses_supplied_evidence_dimensions():
    result = evaluate_contextual_change(_current(), _comparison(), temporal_evidence=_temporal())
    assert result["status"] == CHANGE_EVIDENCE_ESTABLISHED
    assert result["change_magnitude"]["water_area_deviation_sqkm"] == 5.0
    assert result["change_magnitude"]["water_area_deviation_percentage"] == 50.0
    assert result["evidence_dimensions"]["water_area"]["status"] == "EXPANSION_RELATIVE_TO_SEASONAL_BASELINE"
    assert result["evidence_dimensions"]["boundary_displacement"]["status"] == "NO_DISPLACEMENT_OBSERVED"
    assert result["evidence_dimensions"]["temporal_consistency"]["status"] == "CONSISTENT"


def test_large_expansion_with_cloud_noise_is_not_automatic_warning():
    result = evaluate_contextual_change(
        _current(cloud_cover=80),
        _comparison(current=40.0, baseline=10.0),
        temporal_evidence=_temporal(),
    )
    assert result["status"] == CHANGE_NOT_ESTABLISHED
    assert result["uncertainty"]["level"] == "HIGH"
    assert result["status"] != "CRITICAL"
    assert result["does_not_trigger_glof_warning"] is True


def test_insufficient_temporal_or_quality_evidence_is_explicit():
    current = _current(cloud_cover=80)
    current["data_quality"] = {}
    result = evaluate_contextual_change(current, _comparison(), temporal_evidence={})
    assert result["status"] == CHANGE_NOT_ESTABLISHED
    assert result["uncertainty"]["level"] == "HIGH"
    assert result["evidence_dimensions"]["temporal_consistency"]["status"] == "INSUFFICIENT"
    assert result["evidence_dimensions"]["satellite_quality"]["status"] == "HIGH_UNCERTAINTY"


def test_insufficient_seasonal_baseline_does_not_force_conclusion():
    comparison = _comparison()
    comparison["status"] = "NOT_AVAILABLE"
    comparison["baseline"]["status"] = "INSUFFICIENT_HISTORICAL_DATA"
    result = evaluate_contextual_change(_current(), comparison, temporal_evidence=_temporal())
    assert result["status"] == CHANGE_EVIDENCE_INSUFFICIENT
    assert result["change_magnitude"]["water_area_deviation_sqkm"] is None


if __name__ == "__main__":
    test_meaningful_change_uses_supplied_evidence_dimensions()
    test_large_expansion_with_cloud_noise_is_not_automatic_warning()
    test_insufficient_temporal_or_quality_evidence_is_explicit()
    test_insufficient_seasonal_baseline_does_not_force_conclusion()
    print("Contextual change tests: PASS")