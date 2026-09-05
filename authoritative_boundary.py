"""Trusted reference-boundary validation for named lake identity."""

from copy import deepcopy

from satellite.lake_detection import (
    IDENTITY_SUPPORTED,
    geometry_boundary_distance_km,
    geometry_center,
    geometry_overlap_ratio,
    haversine_km,
)


IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"


REFERENCE_TRUSTED_STATUSES = {"VALIDATED", "AUTHORITATIVE", "TRUSTED"}


def _reference_is_trusted(reference_metadata):
    if not isinstance(reference_metadata, dict):
        return False
    return reference_metadata.get("trust_status") in REFERENCE_TRUSTED_STATUSES or (
        reference_metadata.get("status") in REFERENCE_TRUSTED_STATUSES
    )


def _candidate_center(candidate):
    center = candidate.get("centroid")
    if center:
        return center
    return geometry_center(candidate.get("boundary"))


def _spatial_match(candidate, reference_geometry, *, minimum_iou, maximum_centroid_distance_km, maximum_boundary_distance_km):
    candidate_geometry = candidate.get("boundary")
    reference_iou = geometry_overlap_ratio(candidate_geometry, reference_geometry)
    candidate_center = _candidate_center(candidate)
    reference_center = geometry_center(reference_geometry)
    centroid_distance = haversine_km(candidate_center, reference_center)
    boundary_distance = geometry_boundary_distance_km(
        candidate_geometry, reference_geometry
    )
    accepted = (
        reference_iou is not None
        and reference_iou >= minimum_iou
        and centroid_distance is not None
        and centroid_distance <= maximum_centroid_distance_km
        and boundary_distance is not None
        and boundary_distance <= maximum_boundary_distance_km
    )
    return {
        "accepted": accepted,
        "iou": reference_iou,
        "minimum_iou": minimum_iou,
        "centroid_distance_km": centroid_distance,
        "maximum_centroid_distance_km": maximum_centroid_distance_km,
        "boundary_distance_km": boundary_distance,
        "maximum_boundary_distance_km": maximum_boundary_distance_km,
    }


def _temporal_match(
    temporal_evidence,
    reference_geometry,
    *,
    minimum_iou,
    maximum_centroid_distance_km,
    maximum_boundary_distance_km,
    minimum_observations,
):
    if temporal_evidence is None:
        return {
            "status": "NOT_PROVIDED",
            "accepted": True,
            "observation_count": 0,
            "reason": "No temporal evidence was supplied; spatial validation only",
        }
    tracks = temporal_evidence.get("tracks", []) if isinstance(temporal_evidence, dict) else []
    supported_tracks = []
    for track in tracks:
        observations = track.get("observations", [])
        matches = [
            _spatial_match(
                observation,
                reference_geometry,
                minimum_iou=minimum_iou,
                maximum_centroid_distance_km=maximum_centroid_distance_km,
                maximum_boundary_distance_km=maximum_boundary_distance_km,
            )
            for observation in observations
        ]
        if len(observations) >= minimum_observations and matches and all(
            match["accepted"] for match in matches
        ):
            supported_tracks.append({
                "track_id": track.get("track_id"),
                "observation_count": len(observations),
                "matches": matches,
            })
    accepted = len(supported_tracks) == 1
    return {
        "status": "CONSISTENT" if accepted else "INCONSISTENT",
        "accepted": accepted,
        "observation_count": max(
            (track.get("observation_count", 0) for track in supported_tracks),
            default=0,
        ),
        "supported_tracks": supported_tracks,
        "minimum_observations": minimum_observations,
        "reason": (
            "Exactly one persistent track matches the trusted reference geometry"
            if accepted
            else "No single persistent track consistently matches the trusted reference geometry"
        ),
    }


def validate_authoritative_boundary(
    candidate,
    reference_geometry,
    reference_metadata,
    *,
    temporal_evidence=None,
    minimum_iou=0.70,
    maximum_centroid_distance_km=0.50,
    maximum_boundary_distance_km=0.50,
    minimum_temporal_observations=3,
):
    """Validate a candidate only against explicitly trusted reference geometry."""
    result = {
        "identity_status": IDENTITY_AMBIGUOUS,
        "reference_geometry_trust": (reference_metadata or {}).get(
            "trust_status", (reference_metadata or {}).get("status", "UNTRUSTED")
        ),
        "reference_source": (reference_metadata or {}).get("source"),
        "spatial_validation": None,
        "temporal_validation": None,
        "reason": [],
        "measurement_authority": "WITHHELD",
        "interpretation": "Trusted reference validation is required before authoritative lake measurement.",
    }
    if not _reference_is_trusted(reference_metadata):
        result["reason"].append(
            "Reference geometry is approximate or otherwise not explicitly trusted/validated"
        )
        return result
    if not isinstance(reference_geometry, dict) or not candidate.get("boundary"):
        result["reason"].append("Reference or candidate polygon is missing")
        return result

    spatial = _spatial_match(
        candidate,
        reference_geometry,
        minimum_iou=minimum_iou,
        maximum_centroid_distance_km=maximum_centroid_distance_km,
        maximum_boundary_distance_km=maximum_boundary_distance_km,
    )
    temporal = _temporal_match(
        temporal_evidence,
        reference_geometry,
        minimum_iou=minimum_iou,
        maximum_centroid_distance_km=maximum_centroid_distance_km,
        maximum_boundary_distance_km=maximum_boundary_distance_km,
        minimum_observations=minimum_temporal_observations,
    )
    result["spatial_validation"] = spatial
    result["temporal_validation"] = temporal
    if not spatial["accepted"]:
        result["reason"].append(
            "Candidate failed strict IoU, centroid-distance, or boundary-distance requirements"
        )
    if not temporal["accepted"]:
        result["reason"].append(temporal["reason"])
    if spatial["accepted"] and temporal["accepted"]:
        result["identity_status"] = IDENTITY_SUPPORTED
        result["measurement_authority"] = "AUTHORITATIVE_REFERENCE_VALIDATED"
        result["reason"] = [
            "Candidate satisfies strict trusted-reference spatial validation"
            + (" and supplied temporal consistency validation" if temporal_evidence is not None else "")
        ]
    return result


def apply_authoritative_validation(candidate_detection, reference_geometry, reference_metadata, **kwargs):
    """Attach optional authoritative evidence without promoting approximate ROIs."""
    result = deepcopy(candidate_detection)
    selected = result.get("selected_candidate") or {}
    validation = validate_authoritative_boundary(
        selected,
        reference_geometry,
        reference_metadata,
        **kwargs,
    )
    result["authoritative_boundary_validation"] = validation
    result["identity_status"] = validation["identity_status"]
    result["reason"] = validation["reason"]
    return result


def build_observed_area_measurement(
    validation,
    area_result,
    satellite_observation,
    *,
    boundary,
    measurement_scope="VALIDATED_TSHO_ROLPA_OPEN_WATER",
):
    """Publish an area only after trusted identity and real-image gates pass."""
    satellite_observation = satellite_observation or {}
    image_id = satellite_observation.get("image_id")
    acquisition_time = satellite_observation.get("acquisition_time")
    provenance = satellite_observation.get("provenance") or {}
    valid_satellite_provenance = provenance.get("type") in {
        "REAL_SATELLITE_DATA",
        "DERIVED_FROM_REAL_DATA",
    }
    valid_satellite = (
        satellite_observation.get("status") == "SUCCESS"
        and satellite_observation.get("validity_status", "VALID") != "UNAVAILABLE"
        and image_id
        and acquisition_time
        and valid_satellite_provenance
    )
    area_is_valid = (
        isinstance(area_result, dict)
        and area_result.get("status") == "SUCCESS"
        and isinstance(area_result.get("area_sqkm"), (int, float))
        and boundary is not None
    )
    if (
        not isinstance(validation, dict)
        or validation.get("identity_status") != IDENTITY_SUPPORTED
        or validation.get("measurement_authority") != "AUTHORITATIVE_REFERENCE_VALIDATED"
        or not valid_satellite
        or not area_is_valid
    ):
        return {
            "status": "UNAVAILABLE",
            "area_sqkm": None,
            "measurement_scope": "WITHHELD_IDENTITY_OR_IMAGERY_INSUFFICIENT",
            "identity_status": (validation or {}).get("identity_status", IDENTITY_AMBIGUOUS),
            "authoritative_boundary_validation": deepcopy(validation),
            "provenance": deepcopy(provenance),
            "reason": "Authoritative observed area withheld because identity, imagery, provenance, or measurement validity failed",
        }
    return {
        "status": "SUPPORTED_SATELLITE_OBSERVED_OPEN_WATER",
        "area_sqkm": area_result["area_sqkm"],
        "boundary": deepcopy(boundary),
        "measurement_scope": measurement_scope,
        "identity_status": IDENTITY_SUPPORTED,
        "image_id": image_id,
        "acquisition_time": acquisition_time,
        "authoritative_boundary_validation": deepcopy(validation),
        "provenance": deepcopy(provenance),
        "limitations": [
            "Observed open-water extent only; not permanent lake area, volume, or GLOF probability",
            "Area is publishable only because a trusted reference boundary and temporal gate were supplied",
        ],
    }