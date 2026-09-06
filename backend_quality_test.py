"""Regression checks for provenance, geometry scope, and API honesty."""

import os
import tempfile
from unittest.mock import patch

from app import app
from main import (
    _acquisition_is_in_requested_range,
    _integrated_result_skeleton,
    _data_confidence_summary,
    _previous_observation_change,
    _risk_change_explanation,
    run_integrated_monitoring,
    run_tsho_rolpa_temporal_evidence,
)
from observation_store import ObservationStore
from provenance import DERIVED_FROM_REAL_DATA, UNAVAILABLE
from risk_engine import RiskEngine
from satellite.lake_detection import (
    IDENTITY_SUPPORTED,
    IDENTITY_UNCERTAIN,
    assess_target_identity,
    build_temporal_tracks,
    can_publish_observed_area,
    evaluate_temporal_identity,
    select_candidate,
)
from satellite.ndwi_analysis import NDWIAnalyzer
from satellite.region_config import get_lake_geometry, get_monitoring_metadata, get_region_info


def test_geometry_and_provenance_contract():
    result = _integrated_result_skeleton("Tsho_Rolpa_Nepal", status="ERROR")
    assert result["geometry"]["status"] == "APPROXIMATE"
    assert result["geometry"]["measurement_scope"] == "UNKNOWN"
    assert result["provenance"]["type"] == UNAVAILABLE
    assert get_region_info("Tsho_Rolpa_Nepal")["geometry_status"] == "APPROXIMATE"
    geometry, metadata = get_lake_geometry("not-a-lake")
    assert geometry is None
    assert metadata["status"] == "UNKNOWN"


def test_acquisition_period_is_explicit():
    assert _acquisition_is_in_requested_range(1757970000000, "2025-09-01", "2025-10-01")
    assert not _acquisition_is_in_requested_range(1756688400000, "2025-09-01", "2025-10-01")


def test_missing_risk_inputs_are_not_safe():
    assessment = RiskEngine().assess_risk()
    assert assessment["risk_level"] == "UNKNOWN"
    assert assessment["decision_support_status"] == "INSUFFICIENT_DATA"
    assert assessment["missing_inputs"] == ["satellite", "ai", "sensor"]
    assert "No observations available" in assessment["explanation"]


def test_metadata_does_not_parse_prose_as_population():
    metadata = get_monitoring_metadata()
    assert metadata["total_people_at_risk"] is None


def test_ndwi_configuration_is_used():
    previous = os.environ.get("NDWI_WATER_THRESHOLD")
    os.environ["NDWI_WATER_THRESHOLD"] = "0.42"
    try:
        assert NDWIAnalyzer().ndwi_water_threshold == 0.42
    finally:
        if previous is None:
            os.environ.pop("NDWI_WATER_THRESHOLD", None)
        else:
            os.environ["NDWI_WATER_THRESHOLD"] = previous


def test_api_rejects_invalid_risk_input():
    client = app.test_client()
    response = client.post("/api/demo/risk-engine", json={"satellite_signal": "bad"})
    assert response.status_code == 400


def test_candidate_identity_requires_discriminating_evidence():
    center = {"latitude": 27.861, "longitude": 86.476}
    roi = {
        "min_longitude": 86.45,
        "max_longitude": 86.50,
        "min_latitude": 27.84,
        "max_latitude": 27.88,
    }
    candidate = {
        "candidate_id": "component_1",
        "area_sqkm": 1.2,
        "centroid": center,
        "bounds": {
            "min_longitude": 86.46,
            "max_longitude": 86.49,
            "min_latitude": 27.85,
            "max_latitude": 27.875,
        },
        "mean_ndwi": 0.55,
        "compactness": 0.4,
    }
    supported = select_candidate([candidate], center, roi, 0.3, 0.9)
    assert supported["identity_status"] == IDENTITY_SUPPORTED
    assert supported["selected_candidate"]["evidence"]["reference_overlap"] == "UNAVAILABLE"

    ambiguous = select_candidate(
        [candidate, {**candidate, "candidate_id": "component_2"}],
        center,
        roi,
        0.3,
        0.9,
    )
    assert ambiguous["identity_status"] == IDENTITY_UNCERTAIN
    assert any("Competing water candidates" in reason for reason in ambiguous["reason"])


def test_temporal_tracks_preserve_persistent_ambiguity():
    observations = []
    for index, date in enumerate(("2026-04-01", "2026-04-21", "2026-05-26")):
        observations.append({
            "image_id": f"image_{index}",
            "acquisition_time": date,
            "candidates": [
                {"candidate_id": "near", "centroid": {"latitude": 27.861, "longitude": 86.476}, "area_sqkm": 1.0, "evidence": {"valid_pixel_fraction": 0.9}, "quality": {"valid_pixel_fraction": 0.9}},
                {"candidate_id": "other", "centroid": {"latitude": 27.852, "longitude": 86.486}, "area_sqkm": 0.5, "evidence": {"valid_pixel_fraction": 0.9}, "quality": {"valid_pixel_fraction": 0.9}},
            ],
        })
    tracks = build_temporal_tracks(observations)
    evidence = evaluate_temporal_identity(
        tracks, {"latitude": 27.861, "longitude": 86.476}
    )
    assert evidence["status"] == "TEMPORAL_IDENTITY_AMBIGUOUS"
    assert evidence["near_persistent_track_count"] == 2
    assert all(track["observation_count"] == 3 for track in tracks["tracks"])


def test_identity_logic_is_not_tsho_rolpa_hardcoded():
    center = {"latitude": 30.0, "longitude": 90.0}
    roi = {
        "min_longitude": 89.95,
        "max_longitude": 90.05,
        "min_latitude": 29.95,
        "max_latitude": 30.05,
    }
    candidate = {
        "candidate_id": "other_lake_component",
        "area_sqkm": 1.0,
        "centroid": center,
        "bounds": {
            "min_longitude": 89.97,
            "max_longitude": 90.03,
            "min_latitude": 29.97,
            "max_latitude": 30.03,
        },
        "mean_ndwi": 0.55,
        "compactness": 0.4,
        "valid_pixel_fraction": 0.9,
    }
    result = select_candidate(
        [candidate], center, roi, 0.3, 0.9, target_name="Example Lake"
    )
    assert result["identity_status"] == IDENTITY_SUPPORTED

    temporal = evaluate_temporal_identity(
        {"tracks": []}, center, target_name="Example Lake"
    )
    assert "Example Lake" in temporal["reasons"][0]


def test_supported_identity_requires_stable_boundary_track():
    boundary = {
        "type": "Polygon",
        "coordinates": [[[89.97, 29.97], [90.03, 29.97], [90.03, 30.03], [89.97, 30.03], [89.97, 29.97]]],
    }
    observations = [
        {
            "image_id": f"clear_{index}",
            "acquisition_time": f"2026-06-0{index + 1}",
            "candidates": [{
                "candidate_id": f"candidate_{index}",
                "centroid": {"latitude": 30.0, "longitude": 90.0},
                "boundary": boundary,
                "area_sqkm": 1.0,
                "evidence": {"valid_pixel_fraction": 0.9},
                "quality": {"valid_pixel_fraction": 0.9},
            }],
        }
        for index in range(3)
    ]
    tracks = build_temporal_tracks(observations)
    assessment = assess_target_identity(
        tracks, {"latitude": 30.0, "longitude": 90.0}, target_name="Example Lake"
    )
    assert assessment["identity_status"] == IDENTITY_SUPPORTED
    assert assessment["tracks"][0]["observation_count"] == 3


def test_ambiguous_identity_withholds_measurement_semantics():
    boundary = {
        "type": "Polygon",
        "coordinates": [[[89.97, 29.97], [90.03, 29.97], [90.03, 30.03], [89.97, 30.03], [89.97, 29.97]]],
    }
    competing_boundary = {
        "type": "Polygon",
        "coordinates": [[[89.98, 29.98], [90.04, 29.98], [90.04, 30.04], [89.98, 30.04], [89.98, 29.98]]],
    }
    observations = [
        {
            "image_id": f"ambiguous_{index}",
            "candidates": [
                {"candidate_id": "a", "centroid": {"latitude": 30.0, "longitude": 90.0}, "boundary": boundary, "area_sqkm": 1.0, "evidence": {"valid_pixel_fraction": 0.9}, "quality": {"valid_pixel_fraction": 0.9}},
                {"candidate_id": "b", "centroid": {"latitude": 30.01, "longitude": 90.01}, "boundary": competing_boundary, "area_sqkm": 0.8, "evidence": {"valid_pixel_fraction": 0.9}, "quality": {"valid_pixel_fraction": 0.9}},
            ],
        }
        for index in range(3)
    ]
    assessment = assess_target_identity(
        build_temporal_tracks(observations),
        {"latitude": 30.0, "longitude": 90.0},
        target_name="Example Lake",
    )
    assert assessment["identity_status"] == "IDENTITY_AMBIGUOUS"
    assert assessment["near_persistent_track_count"] > 1
    assert not can_publish_observed_area(
        assessment["identity_status"], {"status": "SUCCESS", "area_sqkm": 1.0}, boundary
    )


def test_supported_identity_allows_valid_observed_area_only():
    boundary = {
        "type": "Polygon",
        "coordinates": [[[89.97, 29.97], [90.03, 29.97], [90.03, 30.03], [89.97, 30.03], [89.97, 29.97]]],
    }
    assert can_publish_observed_area(
        IDENTITY_SUPPORTED, {"status": "SUCCESS", "area_sqkm": 1.0}, boundary
    )
    assert not can_publish_observed_area(
        IDENTITY_SUPPORTED, {"status": "NO_VALID_PIXELS", "area_sqkm": None}, boundary
    )


def _observation_fixture(status="IDENTITY_AMBIGUOUS"):
    return {
        "status": status,
        "region": "Tsho_Rolpa_Nepal",
        "mode": "monitoring",
        "decision_support": {
            "status": "IDENTITY_UNCERTAIN",
            "reason": "candidate identity is unresolved",
            "risk_available": False,
        },
        "satellite": {
            "status": status,
            "image_id": "fixture-image",
            "acquisition_time": "2026-05-26T05:00:59+00:00",
            "candidate_detection": {"identity_status": status},
            "water_area": None,
        },
        "observed_measurement": {
            "status": "UNAVAILABLE",
            "area_sqkm": None,
            "provenance": {"type": UNAVAILABLE},
        },
        "provenance": {"type": DERIVED_FROM_REAL_DATA, "source": "fixture"},
    }


def test_observation_persistence_and_retrieval():
    with tempfile.TemporaryDirectory() as directory:
        database_path = os.path.join(directory, "observations.sqlite3")
        previous = os.environ.get("G_ALERT_OBSERVATIONS_DB")
        os.environ["G_ALERT_OBSERVATIONS_DB"] = database_path
        try:
            fixture = _observation_fixture()
            with patch("main._run_integrated_monitoring", return_value=fixture):
                result = run_integrated_monitoring("Tsho_Rolpa_Nepal")
            assert result["persistence"]["status"] == "SAVED"
            records = ObservationStore(database_path).list("Tsho_Rolpa_Nepal")
            assert len(records) == 1
            assert records[0]["observation_id"] == result["observation_id"]
            assert records[0]["decision_support_status"] == "IDENTITY_UNCERTAIN"
            assert records[0]["observation"]["provenance"]["source"] == "fixture"
            response = app.test_client().get("/api/observations/Tsho_Rolpa_Nepal")
            assert response.status_code == 200
            assert response.get_json()["count"] == 1
        finally:
            if previous is None:
                os.environ.pop("G_ALERT_OBSERVATIONS_DB", None)
            else:
                os.environ["G_ALERT_OBSERVATIONS_DB"] = previous


def test_observation_store_rejects_area_without_supported_identity():
    with tempfile.TemporaryDirectory() as directory:
        store = ObservationStore(os.path.join(directory, "observations.sqlite3"))
        invalid = _observation_fixture()
        invalid["observed_measurement"] = {
            "status": "SUPPORTED_SATELLITE_OBSERVED_OPEN_WATER",
            "area_sqkm": 1.0,
        }
        try:
            store.save(invalid)
        except ValueError as exc:
            assert "IDENTITY_SUPPORTED" in str(exc)
        else:
            raise AssertionError("invalid identity-area combination was persisted")


def test_previous_valid_observation_change_is_separate_from_seasonal_baseline():
    with tempfile.TemporaryDirectory() as directory:
        store = ObservationStore(os.path.join(directory, "observations.sqlite3"))
        previous = _observation_fixture()
        previous["status"] = "SUCCESS"
        previous["validity_status"] = "VALID"
        previous["satellite"]["status"] = "SUCCESS"
        previous["satellite"]["acquisition_time"] = "2026-05-25T05:00:00+00:00"
        previous["satellite"]["water_area"] = {"status": "SUCCESS", "area_sqkm": 10.0}
        previous["observed_measurement"] = {
            "status": "UNAVAILABLE",
            "area_sqkm": None,
            "provenance": {"type": UNAVAILABLE},
        }
        store.save(previous)

        current = _observation_fixture()
        current["status"] = "SUCCESS"
        current["validity_status"] = "VALID"
        current["satellite"]["status"] = "SUCCESS"
        current["satellite"]["quality_masking"] = {"status": "APPLIED"}
        current["satellite"]["data_quality"] = {
            "confidence": 0.9,
            "valid_pixel_fraction": 0.9,
        }
        current["satellite"]["water_area"] = {"status": "SUCCESS", "area_sqkm": 12.0}
        current["satellite"]["seasonal_comparison"] = {
            "status": "VALID",
            "baseline_value": 9.0,
            "deviation_percentage": 33.3333333333,
            "baseline": {"statistics": {"mean": 9.0}},
        }
        current["observed_measurement"] = {
            "status": "UNAVAILABLE",
            "area_sqkm": None,
            "provenance": {"type": UNAVAILABLE},
        }
        current["decision_support"] = {
            "status": "PROTOTYPE_ASSESSMENT",
            "risk_available": True,
        }
        current["risk"] = {
            "risk_level": "SAFE",
            "assessment_status": "COMPLETE",
            "decision_support_status": "MULTI_SIGNAL",
            "confidence": "PROTOTYPE_LIMITED",
            "unavailable_information": [],
            "simulated_signals": [],
            "assumptions": [],
            "explanation": "test evidence",
        }
        change = _previous_observation_change(store, "Tsho_Rolpa_Nepal", 12.0)
        assert change["previous_area_sqkm"] == 10.0
        assert change["current_area_sqkm"] == 12.0
        assert change["previous_observation_percent_change"] == 20.0
        assert change["trend"] == "INCREASING"
        assert current["satellite"]["seasonal_comparison"]["baseline_value"] == 9.0
        assert current["satellite"]["seasonal_comparison"]["baseline_value"] != change["previous_area_sqkm"]


def test_previous_invalid_observations_are_skipped():
    with tempfile.TemporaryDirectory() as directory:
        store = ObservationStore(os.path.join(directory, "observations.sqlite3"))
        invalid = _observation_fixture()
        invalid["status"] = "SUCCESS"
        invalid["validity_status"] = "VALID"
        invalid["satellite"]["status"] = "SUCCESS"
        invalid["satellite"]["water_area"] = {"status": "NO_VALID_PIXELS", "area_sqkm": None}
        store.save(invalid)
        assert store.get_previous_valid_observation("Tsho_Rolpa_Nepal") is None


def test_risk_change_explanation_compares_previous_valid_result():
    with tempfile.TemporaryDirectory() as directory:
        store = ObservationStore(os.path.join(directory, "observations.sqlite3"))
        previous = _observation_fixture()
        previous.update({"status": "SUCCESS", "validity_status": "VALID"})
        previous["satellite"].update({
            "status": "SUCCESS",
            "water_area": {"status": "SUCCESS", "area_sqkm": 10.0},
        })
        previous["satellite_change"] = {
            "current_area_sqkm": 10.0,
            "previous_observation_percent_change": None,
            "trend": None,
            "status": "NOT_AVAILABLE",
        }
        previous["risk"] = {
            "risk_score": 0.2,
            "risk_level": "SAFE",
            "assessment_status": "COMPLETE",
            "confidence": "PROTOTYPE_LIMITED",
            "signals": {"satellite": 0.2},
            "missing_inputs": [],
            "unavailable_information": [],
        }
        store.save(previous)

        current = {
            "status": "SUCCESS",
            "validity_status": "VALID",
            "satellite": {"acquisition_time": "2026-09-05T05:00:00+00:00"},
            "satellite_change": {
                "current_area_sqkm": 12.0,
                "previous_observation_percent_change": 20.0,
                "trend": "INCREASING",
                "status": "CALCULATED",
                "data_quality_confidence": 0.8,
            },
            "risk": {
                "risk_score": 0.5,
                "risk_level": "WARNING",
                "assessment_status": "COMPLETE",
                "confidence": "LIMITED",
                "signals": {"satellite": 0.5},
                "missing_inputs": [],
                "unavailable_information": [],
            },
        }
        result = _risk_change_explanation(store, "Tsho_Rolpa_Nepal", current)
        assert result["status"] == "CALCULATED"
        assert result["previous_risk_score"] == 0.2
        assert result["current_risk_score"] == 0.5
        assert result["previous_risk_level"] == "SAFE"
        assert result["current_risk_level"] == "WARNING"
        assert result["previous_risk_status"] == "COMPLETE"
        assert result["current_risk_status"] == "COMPLETE"
        assert result["trend"] == "INCREASING"
        assert result["score_change"] == 0.3
        assert result["contributing_changes"]["lake_area"]["percent_change"] == 20.0
        assert "Risk score changed" in result["explanation"]


def test_unified_data_confidence_summary_is_not_risk_probability():
    observation = {
        "status": "SUCCESS",
        "provenance": {
            "type": DERIVED_FROM_REAL_DATA,
            "source": "Sentinel-2",
            "limitations": [],
        },
        "satellite": {
            "status": "SUCCESS",
            "quality_masking": {"status": "APPLIED"},
            "data_quality": {"confidence": 0.9, "valid_pixel_fraction": 0.9},
            "candidate_detection": {"identity_status": "IDENTITY_SUPPORTED"},
            "seasonal_comparison": {
                "status": "VALID",
                "baseline": {"observation_count": 4},
            },
        },
        "risk": {
            "missing_inputs": [],
            "unavailable_information": [],
            "assumptions": [],
        },
    }
    summary = _data_confidence_summary(observation)
    assert summary["level"] == "HIGH"
    assert summary["is_probability"] is False
    assert summary["factors"]["imagery_quality"]["status"] == "AVAILABLE"
    assert summary["factors"]["lake_identity"]["quality"] == "HIGH"
    assert summary["factors"]["historical_baseline"]["quality"] == "HIGH"

    observation["satellite"]["candidate_detection"]["identity_status"] = "IDENTITY_AMBIGUOUS"
    observation["satellite"]["seasonal_comparison"]["status"] = "NOT_AVAILABLE"
    degraded = _data_confidence_summary(observation)
    assert degraded["level"] == "LOW"
    assert degraded["reasons"]
    assert any("lake identity" in reason for reason in degraded["reasons"])


def test_temporal_evidence_persistence_and_retrieval():
    with tempfile.TemporaryDirectory() as directory:
        database_path = os.path.join(directory, "observations.sqlite3")
        store = ObservationStore(database_path)
        evidence_run = {
            "status": "SUCCESS",
            "region": "Tsho_Rolpa_Nepal",
            "requested_date_range": {"start": "2026-03-01", "end": "2026-09-06"},
            "observations": [
                {"image_id": "image-a", "acquisition_time": "2026-03-01", "quality": {"valid_pixel_fraction": 0.9}},
                {"image_id": "image-b", "acquisition_time": "2026-05-01", "quality": {"valid_pixel_fraction": 0.8}},
            ],
            "temporal_evidence": {
                "identity_status": "IDENTITY_AMBIGUOUS",
                "status": "TEMPORAL_IDENTITY_AMBIGUOUS",
                "tracks": [],
            },
            "provenance": {"type": DERIVED_FROM_REAL_DATA, "source": "fixture"},
        }
        record = store.save_temporal_evidence(evidence_run)
        runs = store.list_temporal_evidence("Tsho_Rolpa_Nepal")
        assert record["run_id"] == runs[0]["run_id"]
        assert runs[0]["identity_status"] == "IDENTITY_AMBIGUOUS"
        assert runs[0]["observation_count"] == 2
        assert runs[0]["evidence_run"]["provenance"]["source"] == "fixture"

        previous = os.environ.get("G_ALERT_OBSERVATIONS_DB")
        os.environ["G_ALERT_OBSERVATIONS_DB"] = database_path
        try:
            response = app.test_client().get("/api/observations/Tsho_Rolpa_Nepal/temporal")
            assert response.status_code == 200
            assert response.get_json()["count"] == 1
        finally:
            if previous is None:
                os.environ.pop("G_ALERT_OBSERVATIONS_DB", None)
            else:
                os.environ["G_ALERT_OBSERVATIONS_DB"] = previous


def test_temporal_wrapper_persists_ambiguous_result():
    fixture = {
        "status": "SUCCESS",
        "region": "Tsho_Rolpa_Nepal",
        "observations": [],
        "temporal_evidence": {"identity_status": "IDENTITY_AMBIGUOUS"},
    }
    with tempfile.TemporaryDirectory() as directory:
        database_path = os.path.join(directory, "observations.sqlite3")
        previous = os.environ.get("G_ALERT_OBSERVATIONS_DB")
        os.environ["G_ALERT_OBSERVATIONS_DB"] = database_path
        try:
            with patch("main._run_tsho_rolpa_temporal_evidence", return_value=fixture):
                result = run_tsho_rolpa_temporal_evidence("2026-03-01", "2026-09-06")
            assert result["persistence"]["status"] == "SAVED"
            assert ObservationStore(database_path).list_temporal_evidence("Tsho_Rolpa_Nepal")[0]["identity_status"] == "IDENTITY_AMBIGUOUS"
        finally:
            if previous is None:
                os.environ.pop("G_ALERT_OBSERVATIONS_DB", None)
            else:
                os.environ["G_ALERT_OBSERVATIONS_DB"] = previous


if __name__ == "__main__":
    test_geometry_and_provenance_contract()
    test_missing_risk_inputs_are_not_safe()
    test_metadata_does_not_parse_prose_as_population()
    test_ndwi_configuration_is_used()
    test_api_rejects_invalid_risk_input()
    test_candidate_identity_requires_discriminating_evidence()
    test_temporal_tracks_preserve_persistent_ambiguity()
    test_identity_logic_is_not_tsho_rolpa_hardcoded()
    test_supported_identity_requires_stable_boundary_track()
    test_ambiguous_identity_withholds_measurement_semantics()
    test_supported_identity_allows_valid_observed_area_only()
    test_observation_persistence_and_retrieval()
    test_observation_store_rejects_area_without_supported_identity()
    test_temporal_evidence_persistence_and_retrieval()
    test_temporal_wrapper_persists_ambiguous_result()
    print("Backend quality checks: PASS")
