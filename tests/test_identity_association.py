"""Focused tests for fragmented temporal identity association."""

from satellite.identity_association import associate_temporal_identity


def _boundary(longitude, latitude, size=0.004):
    return {"type": "Polygon", "coordinates": [[[longitude, latitude], [longitude + size, latitude], [longitude + size, latitude + size], [longitude, latitude + size], [longitude, latitude]]]}


def _candidate(candidate_id, longitude, latitude, area=1.0):
    return {
        "candidate_id": candidate_id,
        "centroid": {"longitude": longitude, "latitude": latitude},
        "boundary": _boundary(longitude - 0.002, latitude - 0.002),
        "area_sqkm": area,
        "compactness": 0.4,
        "mean_ndwi": 0.55,
        "evidence": {"valid_pixel_fraction": 0.9},
    }


def _history(points):
    return [{"image_id": f"image-{index}", "candidates": [_candidate(f"h-{index}", *point)]} for index, point in enumerate(points)]


def test_clean_one_to_one_historical_centroid_association():
    result = associate_temporal_identity(
        [_candidate("current", 86.4705, 27.8605)],
        _history([(86.47, 27.86), (86.4702, 27.8602), (86.4698, 27.8598)]),
    )
    assert result["identity_status"] == "IDENTITY_TEMPORAL_VALID"
    assert result["association_status"] == "SINGLE_ASSOCIATED"
    assert result["measurement_permitted"] is False


def test_three_fragments_form_derived_compound_observation():
    history = _history([(86.47, 27.86), (86.4702, 27.8602), (86.4698, 27.8598)])
    current = [
        _candidate("fragment-a", 86.469, 27.859),
        _candidate("fragment-b", 86.471, 27.861),
        _candidate("fragment-c", 86.470, 27.860),
    ]
    result = associate_temporal_identity(current, history)
    assert result["identity_status"] == "IDENTITY_TEMPORAL_VALID"
    assert result["compound_observation"]["component_count"] == 3
    assert result["compound_observation"]["geometry_union_is_derived_evidence"] is True


def test_unrelated_mountain_shadow_is_rejected():
    result = associate_temporal_identity(
        [_candidate("shadow", 86.49, 27.88)],
        _history([(86.47, 27.86), (86.4702, 27.8602), (86.4698, 27.8598)]),
    )
    assert result["identity_status"] == "IDENTITY_AMBIGUOUS"
    assert result["rejected_candidates"]


def test_two_nearby_distinct_water_bodies_remain_separate():
    result = associate_temporal_identity(
        [_candidate("lake-a", 86.470, 27.860), _candidate("lake-b", 86.476, 27.866)],
        _history([(86.47, 27.86), (86.4702, 27.8602), (86.4698, 27.8598)]),
    )
    assert result["identity_status"] == "IDENTITY_AMBIGUOUS"
    assert result["association_status"] == "COMPETING_CURRENT_GROUPS"


def test_insufficient_history_remains_ambiguous():
    result = associate_temporal_identity(
        [_candidate("current", 86.47, 27.86)],
        _history([(86.47, 27.86), (86.4702, 27.8602)]),
    )
    assert result["identity_status"] == "IDENTITY_AMBIGUOUS"
    assert result["measurement_permitted"] is False


if __name__ == "__main__":
    test_clean_one_to_one_historical_centroid_association()
    test_three_fragments_form_derived_compound_observation()
    test_unrelated_mountain_shadow_is_rejected()
    test_two_nearby_distinct_water_bodies_remain_separate()
    test_insufficient_history_remains_ambiguous()
    print("Identity association tests: PASS")
