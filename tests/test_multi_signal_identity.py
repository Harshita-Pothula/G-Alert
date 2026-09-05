"""Focused tests for conservative multi-signal identity evaluation."""

from satellite.multi_signal_identity import (
    IDENTITY_TEMPORAL_VALID,
    evaluate_multi_signal_identity,
)
from satellite_cross_validation import SATELLITES_AGREE, SATELLITES_DISAGREE, NO_INDEPENDENT_DATA


REFERENCE_VALIDATION = {
    "identity_status": "IDENTITY_SUPPORTED",
    "measurement_authority": "AUTHORITATIVE_REFERENCE_VALIDATED",
    "reference_geometry_trust": "AUTHORITATIVE",
    "spatial_validation": {"iou": 0.91},
    "temporal_validation": {"status": "CONSISTENT"},
}


def _candidate(valid_fraction=0.9, competing=False):
    selected = {
        "candidate_id": "candidate-1",
        "centroid": {"latitude": 27.86, "longitude": 86.47},
        "area_sqkm": 1.3,
        "valid_pixel_fraction": valid_fraction,
        "evidence": {"score_gap_to_next_candidate": 0.3},
    }
    candidates = [selected]
    if competing:
        candidates.append({"candidate_id": "candidate-2", "area_sqkm": 1.2})
        selected["evidence"]["score_gap_to_next_candidate"] = 0.05
    return {"identity_status": "IDENTITY_UNCERTAIN", "selected_candidate": selected, "candidates": candidates}


def _temporal(count=4, persistent=1):
    return {
        "usable_observation_ids": [f"image-{index}" for index in range(count)],
        "tracks": [{"track_id": f"track-{index}", "observation_count": 4} for index in range(persistent)],
    }


def _cross(status):
    return {"status": status, "uncertainty": {"confidence": "INDEPENDENT_CORROBORATION"}}


def test_strong_temporal_and_agreement_with_trusted_reference():
    result = evaluate_multi_signal_identity(
        candidate_detection=_candidate(),
        temporal_evidence=_temporal(),
        satellite_cross_validation=_cross(SATELLITES_AGREE),
        authoritative_validation=REFERENCE_VALIDATION,
        primary_provenance={"type": "DERIVED_FROM_REAL_DATA", "source": "Sentinel-2"},
    )
    assert result["identity_status"] == "IDENTITY_SUPPORTED"
    assert result["measurement_permitted"] is True
    assert result["confidence"] == "HIGH"
    assert "independent satellite agreement" in result["supporting_signals"]


def test_temporal_valid_without_landsat_remains_supported_only_with_reference():
    result = evaluate_multi_signal_identity(
        candidate_detection=_candidate(), temporal_evidence=_temporal(),
        satellite_cross_validation=_cross(NO_INDEPENDENT_DATA),
        authoritative_validation=REFERENCE_VALIDATION,
    )
    assert result["temporal_evidence"]["status"] == IDENTITY_TEMPORAL_VALID
    assert result["identity_status"] == "IDENTITY_SUPPORTED"
    assert result["confidence"] == "MODERATE"


def test_satellite_disagreement_is_ambiguous():
    result = evaluate_multi_signal_identity(
        candidate_detection=_candidate(), temporal_evidence=_temporal(),
        satellite_cross_validation=_cross(SATELLITES_DISAGREE),
        authoritative_validation=REFERENCE_VALIDATION,
    )
    assert result["identity_status"] == "IDENTITY_AMBIGUOUS"
    assert result["measurement_permitted"] is False
    assert result["confidence"] == "LOW"


def test_insufficient_temporal_evidence_is_ambiguous():
    result = evaluate_multi_signal_identity(
        candidate_detection=_candidate(), temporal_evidence=_temporal(count=3),
        satellite_cross_validation=_cross(SATELLITES_AGREE),
        authoritative_validation=REFERENCE_VALIDATION,
    )
    assert result["identity_status"] == "IDENTITY_AMBIGUOUS"
    assert result["measurement_permitted"] is False


def test_competing_candidates_and_poor_quality_are_conflicting():
    result = evaluate_multi_signal_identity(
        candidate_detection=_candidate(valid_fraction=0.4, competing=True),
        temporal_evidence=_temporal(),
        satellite_cross_validation=_cross(SATELLITES_AGREE),
        authoritative_validation=REFERENCE_VALIDATION,
    )
    assert result["identity_status"] == "IDENTITY_AMBIGUOUS"
    assert result["conflicting_signals"]


def test_approximate_reference_cannot_unlock_identity():
    result = evaluate_multi_signal_identity(
        candidate_detection=_candidate(), temporal_evidence=_temporal(),
        satellite_cross_validation=_cross(SATELLITES_AGREE),
        authoritative_validation={"identity_status": "IDENTITY_AMBIGUOUS", "reference_geometry_trust": "APPROXIMATE"},
    )
    assert result["identity_status"] == "IDENTITY_AMBIGUOUS"
    assert result["measurement_permitted"] is False
    assert "trusted reference geometry validation" in result["unavailable_signals"]


def test_provenance_and_explanation_are_preserved():
    provenance = {"type": "DERIVED_FROM_REAL_DATA", "source": "Sentinel-2"}
    result = evaluate_multi_signal_identity(
        candidate_detection=_candidate(), temporal_evidence=_temporal(),
        satellite_cross_validation=_cross(NO_INDEPENDENT_DATA),
        authoritative_validation=REFERENCE_VALIDATION,
        primary_provenance=provenance,
    )
    assert result["provenance"] == provenance
    assert result["explanation"]
    assert result["limitations"]


if __name__ == "__main__":
    test_strong_temporal_and_agreement_with_trusted_reference()
    test_temporal_valid_without_landsat_remains_supported_only_with_reference()
    test_satellite_disagreement_is_ambiguous()
    test_insufficient_temporal_evidence_is_ambiguous()
    test_competing_candidates_and_poor_quality_are_conflicting()
    test_approximate_reference_cannot_unlock_identity()
    test_provenance_and_explanation_are_preserved()
    print("Multi-signal identity tests: PASS")