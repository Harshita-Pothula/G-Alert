"""Regression tests for conservative multi-date candidate association."""

from satellite.lake_detection import build_temporal_tracks, evaluate_temporal_identity


def _boundary(longitude, latitude, size=0.01):
    return {
        "type": "Polygon",
        "coordinates": [[
            [longitude, latitude],
            [longitude + size, latitude],
            [longitude + size, latitude + size],
            [longitude, latitude + size],
            [longitude, latitude],
        ]],
    }


def _candidate(candidate_id, longitude, latitude, *, quality=0.9, area=1.2, fragmented=False):
    boundary = _boundary(longitude, latitude)
    return {
        "candidate_id": candidate_id,
        "boundary": boundary,
        "centroid": {"longitude": longitude + 0.005, "latitude": latitude + 0.005},
        "area_sqkm": area,
        "compactness": 0.4,
        "mean_ndwi": 0.55,
        "geometry_part_count": 2 if fragmented else 1,
        "evidence": {
            "valid_pixel_fraction": quality,
            "compactness": 0.4,
            "mean_ndwi": 0.55,
        },
        "quality": {"valid_pixel_fraction": quality},
    }


def test_slightly_shifted_same_lake_is_associated():
    observations = [
        {"image_id": "a", "candidates": [_candidate("a1", 86.46, 27.85)]},
        {"image_id": "b", "candidates": [_candidate("b1", 86.4615, 27.851)]},
        {"image_id": "c", "candidates": [_candidate("c1", 86.4595, 27.8495)]},
    ]
    tracks = build_temporal_tracks(observations)
    assert len(tracks["tracks"]) == 1
    assert tracks["tracks"][0]["observation_count"] == 3
    assert all(
        item.get("temporal_match_evidence", {}).get("accepted")
        for item in observations[1]["candidates"] + observations[2]["candidates"]
    )


def test_fragmented_and_competing_candidates_remain_ambiguous():
    observations = [
        {"image_id": "a", "candidates": [
            _candidate("a1", 86.46, 27.85),
            _candidate("fragmented", 86.461, 27.851, fragmented=True),
            _candidate("a2", 86.48, 27.87),
        ]},
        {"image_id": "b", "candidates": [
            _candidate("b1", 86.461, 27.851),
            _candidate("b2", 86.48, 27.87),
        ]},
        {"image_id": "c", "candidates": [
            _candidate("c1", 86.46, 27.85),
            _candidate("c2", 86.48, 27.87),
        ]},
    ]
    tracks = build_temporal_tracks(observations)
    identity = evaluate_temporal_identity(
        tracks, {"longitude": 86.465, "latitude": 27.855}
    )
    assert tracks["excluded_candidates"]
    assert len(tracks["tracks"]) >= 2
    assert identity["identity_status"] == "IDENTITY_AMBIGUOUS"


def test_poor_quality_candidates_are_excluded_with_reason():
    observations = [{"image_id": "cloudy", "candidates": [_candidate("bad", 86.46, 27.85, quality=0.4)]}]
    tracks = build_temporal_tracks(observations)
    assert tracks["tracks"] == []
    assert tracks["excluded_candidates"][0]["reasons"]
    assert "valid-pixel" in " ".join(tracks["excluded_candidates"][0]["reasons"])


def test_different_nearby_water_body_is_not_merged():
    observations = [
        {"image_id": "a", "candidates": [_candidate("lake", 86.46, 27.85)]},
        {"image_id": "b", "candidates": [_candidate("other", 86.49, 27.88)]},
    ]
    tracks = build_temporal_tracks(observations)
    assert len(tracks["tracks"]) == 2
    assert tracks["rejected_associations"]


def test_insufficient_evidence_remains_conservative():
    observations = [
        {"image_id": "a", "candidates": [_candidate("a", 86.46, 27.85)]},
        {"image_id": "b", "candidates": [_candidate("b", 86.461, 27.851)]},
    ]
    tracks = build_temporal_tracks(observations)
    identity = evaluate_temporal_identity(
        tracks, {"longitude": 86.465, "latitude": 27.855}, min_observations=3
    )
    assert identity["identity_status"] != "IDENTITY_SUPPORTED"
    assert identity["status"] == "TEMPORAL_IDENTITY_NOT_ESTABLISHED"


if __name__ == "__main__":
    test_slightly_shifted_same_lake_is_associated()
    test_fragmented_and_competing_candidates_remain_ambiguous()
    test_poor_quality_candidates_are_excluded_with_reason()
    test_different_nearby_water_body_is_not_merged()
    test_insufficient_evidence_remains_conservative()
    print("Temporal association tests: PASS")
