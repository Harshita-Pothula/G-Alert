"""Focused tests for multi-date seasonal satellite baselines."""

from seasonal_baseline import (
    BASELINE_INSUFFICIENT,
    BASELINE_VALID,
    calculate_seasonal_baseline,
    evaluate_against_seasonal_baseline,
)


def _historical_observations():
    return [
        {
            "image_id": "may-2022",
            "acquisition_time": "2022-05-12T05:00:00+00:00",
            "water_area_sqkm": 10.0,
            "status": "SUCCESS",
            "provenance": {"type": "REAL_SATELLITE_DATA"},
        },
        {
            "image_id": "may-2023",
            "acquisition_time": "2023-05-18T05:00:00+00:00",
            "water_area_sqkm": 12.0,
            "status": "SUCCESS",
            "provenance": {"type": "REAL_SATELLITE_DATA"},
        },
        {
            "image_id": "may-2024",
            "acquisition_time": "2024-05-20T05:00:00+00:00",
            "water_area_sqkm": 14.0,
            "status": "SUCCESS",
            "provenance": {"type": "REAL_SATELLITE_DATA"},
        },
        {
            "image_id": "june-2024",
            "acquisition_time": "2024-06-20T05:00:00+00:00",
            "water_area_sqkm": 99.0,
            "status": "SUCCESS",
        },
    ]


def test_historical_seasonal_baseline_statistics():
    baseline = calculate_seasonal_baseline(
        _historical_observations(), "2026-05-05", minimum_observations=3
    )
    assert baseline["status"] == BASELINE_VALID
    assert baseline["observation_count"] == 3
    assert baseline["statistics"]["mean"] == 12.0
    assert baseline["statistics"]["median"] == 12.0
    assert baseline["statistics"]["minimum"] == 10.0
    assert baseline["statistics"]["maximum"] == 14.0
    assert baseline["statistics"]["range"] == {"minimum": 10.0, "maximum": 14.0}
    assert len(baseline["excluded_observations"]) == 1


def test_current_observation_deviation_is_reported():
    comparison = evaluate_against_seasonal_baseline(
        {
            "image_id": "current",
            "acquisition_time": "2026-05-10T05:00:00+00:00",
            "water_area_sqkm": 15.0,
            "status": "SUCCESS",
        },
        _historical_observations(),
        minimum_observations=3,
    )
    assert comparison["status"] == "VALID"
    assert comparison["baseline_value"] == 12.0
    assert comparison["current_value"] == 15.0
    assert comparison["deviation"] == 3.0
    assert comparison["deviation_percentage"] == 25.0
    assert comparison["provenance"]["type"] == "DERIVED_FROM_REAL_DATA"


def test_insufficient_historical_data_is_explicit():
    comparison = evaluate_against_seasonal_baseline(
        {
            "acquisition_time": "2026-05-10T05:00:00+00:00",
            "water_area_sqkm": 15.0,
            "status": "SUCCESS",
        },
        _historical_observations()[:2],
        minimum_observations=3,
    )
    assert comparison["status"] == "NOT_AVAILABLE"
    assert comparison["baseline_status"] == BASELINE_INSUFFICIENT
    assert comparison["deviation"] is None
    assert comparison["deviation_percentage"] is None
    assert "required" in comparison["reason"]


if __name__ == "__main__":
    test_historical_seasonal_baseline_statistics()
    test_current_observation_deviation_is_reported()
    test_insufficient_historical_data_is_explicit()
    print("Seasonal baseline tests: PASS")