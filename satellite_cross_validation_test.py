"""Focused tests for independent Sentinel-2/Landsat cross-validation."""

from satellite_cross_validation import (
    NO_INDEPENDENT_DATA,
    SATELLITES_AGREE,
    SATELLITES_DISAGREE,
    cross_validate_observation,
)


def _observation(satellite, timestamp, deviation, region="Tsho_Rolpa_Nepal"):
    return {
        "region": region,
        "satellite": {
            "satellite": satellite,
            "image_id": f"{satellite}-image",
            "acquisition_time": timestamp,
            "status": "SUCCESS",
            "water_area": {"area_sqkm": 15.0},
            "quality_masking": {"status": "APPLIED"},
            "provenance": {"type": "REAL_SATELLITE_DATA", "source": satellite},
            "seasonal_comparison": {
                "status": "VALID",
                "current_value": 15.0,
                "baseline_value": 10.0,
                "deviation_percentage": deviation,
                "baseline": {"statistics": {"mean": 10.0}},
            },
        },
        "provenance": {"type": "DERIVED_FROM_REAL_DATA", "source": satellite},
    }


def test_satellites_agree_with_temporal_match_and_anomaly():
    result = cross_validate_observation(
        _observation("Sentinel-2", "2026-09-01T05:00:00+00:00", 50.0),
        _observation("Landsat-8", "2026-09-04T15:00:00+00:00", 45.0),
    )
    assert result["status"] == SATELLITES_AGREE
    assert result["matching"]["matched"] is True
    assert result["evidence"]["primary_anomaly"] is True
    assert result["evidence"]["secondary_anomaly"] is True
    assert result["uncertainty"]["confidence"] == "INDEPENDENT_CORROBORATION"
    assert result["decision_support"]["warning_triggered"] is False


def test_satellites_disagree_and_uncertainty_increases():
    result = cross_validate_observation(
        _observation("Sentinel-2", "2026-09-01T05:00:00+00:00", 50.0),
        _observation("Landsat-9", "2026-09-02T05:00:00+00:00", 2.0),
    )
    assert result["status"] == SATELLITES_DISAGREE
    assert result["uncertainty"]["level"] == "HIGH"
    assert result["uncertainty"]["confidence"] == "CONFLICTING_INDEPENDENT_EVIDENCE"
    assert result["decision_support"]["warning_triggered"] is False


def test_no_independent_data_preserves_primary_integrity():
    result = cross_validate_observation(
        _observation("Sentinel-2", "2026-09-01T05:00:00+00:00", 50.0),
        _observation("Landsat-8", "2026-09-20T05:00:00+00:00", 50.0),
    )
    assert result["status"] == NO_INDEPENDENT_DATA
    assert result["matching"]["matched"] is False
    assert result["uncertainty"]["confidence"] == "PRIMARY_ONLY"
    assert result["primary"]["image_id"] == "Sentinel-2-image"


def test_invalid_secondary_is_no_independent_data():
    secondary = _observation("Landsat-8", "2026-09-02T05:00:00+00:00", 50.0)
    secondary["satellite"]["status"] = "UNAVAILABLE"
    result = cross_validate_observation(
        _observation("Sentinel-2", "2026-09-01T05:00:00+00:00", 50.0),
        secondary,
    )
    assert result["status"] == NO_INDEPENDENT_DATA
    assert result["uncertainty"]["reasons"]


if __name__ == "__main__":
    test_satellites_agree_with_temporal_match_and_anomaly()
    test_satellites_disagree_and_uncertainty_increases()
    test_no_independent_data_preserves_primary_integrity()
    test_invalid_secondary_is_no_independent_data()
    print("Satellite cross-validation tests: PASS")