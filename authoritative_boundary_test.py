"""Focused tests for trusted Tsho Rolpa boundary validation."""

from authoritative_boundary import apply_authoritative_validation, validate_authoritative_boundary
from satellite.lake_detection import IDENTITY_SUPPORTED


IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"


REFERENCE = {
    "type": "Polygon",
    "coordinates": [[[86.46, 27.85], [86.48, 27.85], [86.48, 27.87], [86.46, 27.87], [86.46, 27.85]]],
}
REFERENCE_METADATA = {
    "trust_status": "AUTHORITATIVE",
    "source": "independent validated lake inventory",
}


def _candidate(boundary=REFERENCE):
    return {
        "candidate_id": "component_1",
        "boundary": boundary,
        "centroid": {"longitude": 86.47, "latitude": 27.86},
    }


def _temporal(boundary=REFERENCE):
    return {
        "tracks": [{
            "track_id": "track_1",
            "observations": [
                {"boundary": boundary, "centroid": {"longitude": 86.47, "latitude": 27.86}},
                {"boundary": boundary, "centroid": {"longitude": 86.47, "latitude": 27.86}},
                {"boundary": boundary, "centroid": {"longitude": 86.47, "latitude": 27.86}},
            ],
        }]
    }


def test_high_confidence_match_supports_identity():
    result = validate_authoritative_boundary(
        _candidate(), REFERENCE, REFERENCE_METADATA, temporal_evidence=_temporal()
    )
    assert result["identity_status"] == IDENTITY_SUPPORTED
    assert result["measurement_authority"] == "AUTHORITATIVE_REFERENCE_VALIDATED"
    assert result["spatial_validation"]["iou"] == 1.0
    assert result["temporal_validation"]["status"] == "CONSISTENT"


def test_low_iou_or_spatial_mismatch_remains_ambiguous():
    distant = {
        "type": "Polygon",
        "coordinates": [[[86.60, 27.95], [86.62, 27.95], [86.62, 27.97], [86.60, 27.97], [86.60, 27.95]]],
    }
    result = validate_authoritative_boundary(_candidate(distant), REFERENCE, REFERENCE_METADATA)
    assert result["identity_status"] == IDENTITY_AMBIGUOUS
    assert result["measurement_authority"] == "WITHHELD"
    assert result["spatial_validation"]["iou"] == 0.0


def test_approximate_reference_cannot_unlock_measurement():
    result = validate_authoritative_boundary(
        _candidate(), REFERENCE, {"trust_status": "APPROXIMATE", "source": "analysis ROI"}
    )
    assert result["identity_status"] == IDENTITY_AMBIGUOUS
    assert result["measurement_authority"] == "WITHHELD"
    assert "approximate" in result["reason"][0]


def test_temporal_inconsistency_withholds_measurement():
    inconsistent = {
        "type": "Polygon",
        "coordinates": [[[86.55, 27.90], [86.57, 27.90], [86.57, 27.92], [86.55, 27.92], [86.55, 27.90]]],
    }
    result = validate_authoritative_boundary(
        _candidate(), REFERENCE, REFERENCE_METADATA,
        temporal_evidence=_temporal(inconsistent),
    )
    assert result["identity_status"] == IDENTITY_AMBIGUOUS
    assert result["temporal_validation"]["status"] == "INCONSISTENT"
    assert result["measurement_authority"] == "WITHHELD"


def test_existing_candidate_contract_receives_validation_without_roi_promotion():
    detection = {"identity_status": IDENTITY_AMBIGUOUS, "selected_candidate": _candidate()}
    result = apply_authoritative_validation(
        detection, REFERENCE, REFERENCE_METADATA, temporal_evidence=_temporal()
    )
    assert result["identity_status"] == IDENTITY_SUPPORTED
    approximate = apply_authoritative_validation(
        detection, REFERENCE, {"trust_status": "APPROXIMATE"}
    )
    assert approximate["identity_status"] == IDENTITY_AMBIGUOUS


if __name__ == "__main__":
    test_high_confidence_match_supports_identity()
    test_low_iou_or_spatial_mismatch_remains_ambiguous()
    test_approximate_reference_cannot_unlock_measurement()
    test_temporal_inconsistency_withholds_measurement()
    test_existing_candidate_contract_receives_validation_without_roi_promotion()
    print("Authoritative boundary tests: PASS")