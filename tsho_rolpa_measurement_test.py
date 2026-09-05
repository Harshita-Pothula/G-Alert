"""Focused Tsho Rolpa identity and observed-area contract tests."""

from authoritative_boundary import (
    build_observed_area_measurement,
    validate_authoritative_boundary,
)
from satellite.region_config import get_lake_geometry
from satellite.lake_detection import IDENTITY_SUPPORTED


REFERENCE = {
    "type": "Polygon",
    "coordinates": [[[86.46, 27.85], [86.48, 27.85], [86.48, 27.87], [86.46, 27.87], [86.46, 27.85]]],
}
TRUSTED = {"trust_status": "AUTHORITATIVE", "source": "validated inventory"}


def _candidate(boundary=REFERENCE):
    return {
        "boundary": boundary,
        "centroid": {"longitude": 86.47, "latitude": 27.86},
    }


def _temporal(boundary=REFERENCE):
    return {"tracks": [{"observations": [
        {"boundary": boundary, "centroid": {"longitude": 86.47, "latitude": 27.86}},
        {"boundary": boundary, "centroid": {"longitude": 86.47, "latitude": 27.86}},
        {"boundary": boundary, "centroid": {"longitude": 86.47, "latitude": 27.86}},
    ]}]}


def _satellite(status="SUCCESS"):
    return {
        "status": status,
        "validity_status": "VALID" if status == "SUCCESS" else "UNAVAILABLE",
        "image_id": "20260904T050000_TSHO",
        "acquisition_time": "2026-09-04T05:00:00+00:00",
        "provenance": {"type": "REAL_SATELLITE_DATA", "source": "COPERNICUS/S2_SR_HARMONIZED"},
    }


def _validation(boundary=REFERENCE, metadata=TRUSTED, temporal=None):
    return validate_authoritative_boundary(
        _candidate(boundary), metadata.get("geometry", REFERENCE), metadata,
        temporal_evidence=temporal if temporal is not None else _temporal(),
    )


def test_trusted_matching_candidate_publishes_observed_area():
    validation = _validation()
    measurement = build_observed_area_measurement(
        validation, {"status": "SUCCESS", "area_sqkm": 1.23}, _satellite(), boundary=REFERENCE
    )
    assert validation["identity_status"] == IDENTITY_SUPPORTED
    assert measurement["status"] == "SUPPORTED_SATELLITE_OBSERVED_OPEN_WATER"
    assert measurement["area_sqkm"] == 1.23
    assert measurement["provenance"]["type"] == "REAL_SATELLITE_DATA"
    assert measurement["measurement_scope"] == "VALIDATED_TSHO_ROLPA_OPEN_WATER"


def test_poor_spatial_match_withholds_area():
    distant = {"type": "Polygon", "coordinates": [[[86.60, 27.95], [86.62, 27.95], [86.62, 27.97], [86.60, 27.97], [86.60, 27.95]]]}
    validation = _validation(distant)
    measurement = build_observed_area_measurement(validation, {"status": "SUCCESS", "area_sqkm": 9.9}, _satellite(), boundary=distant)
    assert measurement["status"] == "UNAVAILABLE"
    assert measurement["area_sqkm"] is None


def test_approximate_reference_cannot_unlock_area():
    validation = _validation(metadata={"trust_status": "APPROXIMATE", "source": "analysis ROI"})
    measurement = build_observed_area_measurement(validation, {"status": "SUCCESS", "area_sqkm": 1.23}, _satellite(), boundary=REFERENCE)
    assert measurement["status"] == "UNAVAILABLE"
    assert measurement["area_sqkm"] is None


def test_stale_or_invalid_satellite_withholds_area():
    validation = _validation()
    stale = _satellite("STALE_IMAGERY")
    measurement = build_observed_area_measurement(validation, {"status": "SUCCESS", "area_sqkm": 1.23}, stale, boundary=REFERENCE)
    assert measurement["status"] == "UNAVAILABLE"
    assert measurement["area_sqkm"] is None


def test_temporal_inconsistency_and_insufficient_identity_withhold_area():
    inconsistent = {"type": "Polygon", "coordinates": [[[86.55, 27.90], [86.57, 27.90], [86.57, 27.92], [86.55, 27.92], [86.55, 27.90]]]}
    validation = _validation(temporal=_temporal(inconsistent))
    measurement = build_observed_area_measurement(validation, {"status": "SUCCESS", "area_sqkm": 1.23}, _satellite(), boundary=REFERENCE)
    assert measurement["status"] == "UNAVAILABLE"
    assert measurement["area_sqkm"] is None


def test_repository_has_no_trusted_tsho_rolpa_geometry():
    geometry, metadata = get_lake_geometry("Tsho_Rolpa_Nepal")
    assert geometry is not None
    assert metadata["status"] == "APPROXIMATE"
    assert metadata["geometry_type"] == "APPROXIMATE_ANALYSIS_ROI"
    assert "authoritative" in metadata["source"].lower()
    assert "not bundled" in metadata["source"].lower()


if __name__ == "__main__":
    test_trusted_matching_candidate_publishes_observed_area()
    test_poor_spatial_match_withholds_area()
    test_approximate_reference_cannot_unlock_area()
    test_stale_or_invalid_satellite_withholds_area()
    test_temporal_inconsistency_and_insufficient_identity_withhold_area()
    test_repository_has_no_trusted_tsho_rolpa_geometry()
    print("Tsho Rolpa measurement tests: PASS")