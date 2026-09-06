"""Regression test for the default multi-date temporal acquisition window."""

from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app
from main import (
    _temporal_acquisition_indices,
    _temporal_date_range,
    _temporal_discovery_geometry,
)
from satellite.lake_detection import (
    assess_lake_likeness,
    build_temporal_tracks,
    deduplicate_candidates,
    select_candidate,
)
from satellite.multi_signal_identity import build_evidence_lifecycle
from satellite.region_config import get_authoritative_reference


def test_temporal_default_window_reaches_multiple_acquisitions():
    start_date, end_date = _temporal_date_range(None, None)
    window_days = (
        datetime.strptime(end_date, "%Y-%m-%d")
        - datetime.strptime(start_date, "%Y-%m-%d")
    ).days
    assert window_days == 180
    assert _temporal_acquisition_indices(6, 6) == [0, 1, 2, 3, 4, 5]


def test_approximate_geometry_does_not_constrain_discovery_roi():
    search_geometry = {"type": "Polygon", "coordinates": []}
    approximate_geometry = {"type": "Polygon", "coordinates": [[[1, 1]]]}
    assert _temporal_discovery_geometry(
        search_geometry,
        approximate_geometry,
        {"status": "APPROXIMATE"},
    ) is search_geometry
    assert _temporal_discovery_geometry(
        search_geometry,
        approximate_geometry,
        {"status": "AUTHORITATIVE"},
    ) is approximate_geometry


def test_temporal_quality_gaps_remain_visible_without_breaking_tracks():
    candidate = {
        "candidate_id": "lake-component",
        "centroid": {"longitude": 86.476, "latitude": 27.861},
        "area_sqkm": 1.0,
        "evidence": {"valid_pixel_fraction": 0.9},
        "quality": {"valid_pixel_fraction": 0.9},
    }
    result = build_temporal_tracks([
        {"image_id": "clear-a", "candidates": [candidate]},
        {
            "image_id": "cloudy-b",
            "status": "INSUFFICIENT_QUALITY",
            "reason": "SCL quality masking failed",
            "candidates": [],
        },
        {"image_id": "clear-c", "candidates": [candidate.copy()]},
    ])
    assert result["usable_observation_ids"] == ["clear-a", "clear-c"]
    assert result["degraded_observations"] == [{
        "image_id": "cloudy-b",
        "acquisition_time": None,
        "reason": "SCL quality masking failed",
    }]
    assert result["tracks"][0]["observation_count"] == 2
    assert result["tracks"][0]["gap_count"] == 1


def test_compatible_same_date_fragments_create_derived_tracking_evidence():
    def candidate(candidate_id, longitude):
        boundary = {
            "type": "Polygon",
            "coordinates": [[
                [longitude, 27.86],
                [longitude + 0.004, 27.86],
                [longitude + 0.004, 27.864],
                [longitude, 27.864],
                [longitude, 27.86],
            ]],
        }
        return {
            "candidate_id": candidate_id,
            "boundary": boundary,
            "centroid": {"longitude": longitude + 0.002, "latitude": 27.862},
            "area_sqkm": 0.8,
            "compactness": 0.4,
            "mean_ndwi": 0.55,
            "geometry_part_count": 1,
            "valid_pixel_fraction": 0.9,
            "evidence": {
                "valid_pixel_fraction": 0.9,
                "compactness": 0.4,
                "mean_ndwi": 0.55,
            },
            "quality": {"valid_pixel_fraction": 0.9},
        }

    result = build_temporal_tracks([{
        "image_id": "fragmented-date",
        "candidates": [candidate("fragment-a", 86.470), candidate("fragment-b", 86.474)],
    }])
    assert len(result["compound_observations"]) == 1
    assert result["compound_observations"][0]["component_ids"] == [
        "fragment-a", "fragment-b"
    ]
    assert result["tracks"][0]["observations"][0]["candidate_id"].startswith("compound_")


def test_shape_context_is_evidence_only():
    candidate = {
        "candidate_id": "linear-water",
        "area_sqkm": 1.0,
        "centroid": {"longitude": 86.476, "latitude": 27.861},
        "bounds": {
            "min_longitude": 86.40,
            "max_longitude": 86.50,
            "min_latitude": 27.85,
            "max_latitude": 27.86,
        },
        "mean_ndwi": 0.55,
        "compactness": 0.01,
    }
    result = select_candidate(
        [candidate],
        candidate["centroid"],
        {
            "min_longitude": 86.30,
            "max_longitude": 86.60,
            "min_latitude": 27.80,
            "max_latitude": 27.90,
        },
        0.3,
        0.9,
    )
    evidence = result["selected_candidate"]["evidence"]
    assert evidence["shape_context"] == "POSSIBLE_LINEAR_WATER_FEATURE"
    assert result["identity_status"] == "IDENTITY_SUPPORTED"


def test_temporal_endpoint_accepts_any_configured_region():
    with patch("app.run_temporal_evidence", return_value={
        "status": "SUCCESS",
        "region": "Imja_Tsho_Nepal",
        "observations": [],
    }) as run_temporal:
        response = app.test_client().get("/api/monitor/Imja_Tsho_Nepal/temporal")
    assert response.status_code == 200
    assert response.get_json()["region"] == "Imja_Tsho_Nepal"
    run_temporal.assert_called_once_with("Imja_Tsho_Nepal", None, None, 6)


def test_evidence_lifecycle_separates_candidate_and_authority():
    lifecycle = build_evidence_lifecycle(
        observations=[{
            "candidate_detection": {
                "candidates": [{"candidate_id": "candidate-1"}],
            },
        }],
        temporal_evidence={
            "status": "TEMPORAL_IDENTITY_SUPPORTING",
            "identity_status": "IDENTITY_SUPPORTED",
            "usable_observation_ids": ["image-1", "image-2", "image-3"],
            "persistent_track_count": 1,
        },
        multi_signal_identity={"identity_status": "IDENTITY_AMBIGUOUS"},
        derived_candidate_measurements=[{
            "status": "DERIVED_CANDIDATE_OPEN_WATER",
            "area_sqkm": 0.8,
        }],
        authoritative_measurement={"status": "UNAVAILABLE"},
    )
    assert lifecycle["current_stage"] == "LAKE_LIKE_CANDIDATE"
    assert lifecycle["validated_named_lake"]["status"] == "NOT_VALIDATED"
    assert lifecycle["derived_candidate_measurement"]["status"] == "AVAILABLE"
    assert lifecycle["authoritative_measurement"]["status"] == "WITHHELD"


def test_lake_likeness_is_evidence_only():
    result = assess_lake_likeness([
        {
            "evidence": {
                "spectral_water_support": True,
                "shape_context": "NOT_OBVIOUSLY_LINEAR",
            },
            "spectral_context": {"mndwi": 0.4},
            "terrain_context": {"elevation_m": 4500, "slope_degrees": 3},
        },
    ], {
        "tracks": [{"track_id": "track-1", "observation_count": 3}],
    })
    assert result["status"] == "SUPPORTING"
    assert "one persistent temporal track" in result["evidence"]
    assert result["interpretation"]


def test_reference_validation_is_optional_until_real_metadata_exists():
    geometry, metadata = get_authoritative_reference("Tsho_Rolpa_Nepal")
    assert geometry is None
    assert metadata["trust_status"] == "UNTRUSTED"


def test_cross_tile_deduplication_requires_spatial_overlap():
    boundary = {
        "type": "Polygon",
        "coordinates": [[[86.47, 27.86], [86.48, 27.86], [86.48, 27.87], [86.47, 27.87], [86.47, 27.86]]],
    }
    duplicate = {
        "candidate_id": "tile-b",
        "boundary": boundary,
        "centroid": {"longitude": 86.475, "latitude": 27.865},
    }
    retained = {
        "candidate_id": "tile-a",
        "boundary": boundary,
        "centroid": {"longitude": 86.475, "latitude": 27.865},
    }
    result = deduplicate_candidates([retained, duplicate])
    assert len(result["candidates"]) == 1
    assert result["duplicates"][0]["duplicate_candidate_id"] == "tile-b"


if __name__ == "__main__":
    test_temporal_default_window_reaches_multiple_acquisitions()
    test_approximate_geometry_does_not_constrain_discovery_roi()
    test_temporal_quality_gaps_remain_visible_without_breaking_tracks()
    test_shape_context_is_evidence_only()
    test_temporal_endpoint_accepts_any_configured_region()
    test_evidence_lifecycle_separates_candidate_and_authority()
    print("Temporal acquisition regression test: PASS")