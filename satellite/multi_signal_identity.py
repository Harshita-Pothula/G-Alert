"""Conservative multi-signal lake-identity evaluation."""

from copy import deepcopy

from authoritative_boundary import IDENTITY_AMBIGUOUS, IDENTITY_SUPPORTED
from satellite_cross_validation import (
    NO_INDEPENDENT_DATA,
    SATELLITES_AGREE,
    SATELLITES_DISAGREE,
)


IDENTITY_TEMPORAL_VALID = "IDENTITY_TEMPORAL_VALID"

DISCOVERED_CANDIDATE = "DISCOVERED_CANDIDATE"
PERSISTENT_CANDIDATE = "PERSISTENT_CANDIDATE"
LAKE_LIKE_CANDIDATE = "LAKE_LIKE_CANDIDATE"
VALIDATED_NAMED_LAKE = "VALIDATED_NAMED_LAKE"
AUTHORITATIVE_MEASUREMENT = "AUTHORITATIVE_MEASUREMENT"


def build_evidence_lifecycle(
    *,
    observations=None,
    temporal_evidence=None,
    multi_signal_identity=None,
    authoritative_validation=None,
    derived_candidate_measurements=None,
    authoritative_measurement=None,
):
    """Describe evidence maturity without promoting identity or measurement."""
    observations = observations or []
    temporal = temporal_evidence or {}
    multi_signal = multi_signal_identity or {}
    authoritative = authoritative_validation or {}
    derived_measurements = derived_candidate_measurements or []
    authoritative_result = authoritative_measurement or {}
    candidate_count = sum(
        len((observation.get("candidate_detection") or {}).get("candidates", []))
        for observation in observations
        if isinstance(observation, dict)
    )
    usable_ids = temporal.get("usable_observation_ids") or []
    persistent_count = temporal.get("persistent_track_count", 0)
    temporal_identity = temporal.get("identity_status")
    named_identity = multi_signal.get("identity_status")
    reference_identity = authoritative.get("identity_status")
    authoritative_status = authoritative_result.get("status")

    discovered = bool(candidate_count or observations)
    persistent = persistent_count > 0
    lake_like = persistent and (
        temporal.get("status") == "TEMPORAL_IDENTITY_SUPPORTING"
        or temporal_identity in {"IDENTITY_SUPPORTED", IDENTITY_TEMPORAL_VALID}
    )
    named_validated = (
        named_identity == IDENTITY_SUPPORTED
        or (
            reference_identity == IDENTITY_SUPPORTED
            and authoritative.get("measurement_authority")
            == "AUTHORITATIVE_REFERENCE_VALIDATED"
        )
    )
    authoritative_available = (
        authoritative_status == "SUPPORTED_SATELLITE_OBSERVED_OPEN_WATER"
        and named_validated
    )

    return {
        "current_stage": (
            AUTHORITATIVE_MEASUREMENT
            if authoritative_available
            else VALIDATED_NAMED_LAKE
            if named_validated
            else LAKE_LIKE_CANDIDATE
            if lake_like
            else PERSISTENT_CANDIDATE
            if persistent
            else DISCOVERED_CANDIDATE
            if discovered
            else "NO_SATELLITE_OBJECT"
        ),
        "discovered_object": {
            "status": DISCOVERED_CANDIDATE if discovered else "NOT_ESTABLISHED",
            "observation_count": len(observations),
            "candidate_count": candidate_count,
        },
        "persistent_candidate": {
            "status": PERSISTENT_CANDIDATE if persistent else "NOT_ESTABLISHED",
            "usable_observation_count": len(set(usable_ids)),
            "persistent_track_count": persistent_count,
        },
        "lake_like_candidate": {
            "status": LAKE_LIKE_CANDIDATE if lake_like else "NOT_ESTABLISHED",
            "temporal_identity_status": temporal_identity,
            "reason": (
                "One persistent temporal candidate supports lake-like repeatability"
                if lake_like
                else "Temporal evidence does not establish one lake-like candidate"
            ),
        },
        "validated_named_lake": {
            "status": VALIDATED_NAMED_LAKE if named_validated else "NOT_VALIDATED",
            "identity_status": named_identity or reference_identity or "UNAVAILABLE",
            "reference_status": authoritative.get(
                "measurement_authority", "UNAVAILABLE"
            ),
        },
        "derived_candidate_measurement": {
            "status": "AVAILABLE" if derived_measurements else "UNAVAILABLE",
            "count": len(derived_measurements),
            "scope": "DERIVED_CANDIDATE_OPEN_WATER",
        },
        "authoritative_measurement": {
            "status": "AVAILABLE" if authoritative_available else "WITHHELD",
            "scope": "VALIDATED_NAMED_LAKE_OPEN_WATER",
            "reason": (
                "Trusted named-lake identity and real measurement gates passed"
                if authoritative_available
                else "Authoritative named-lake identity or measurement gates are incomplete"
            ),
        },
    }


def _temporal_signal(temporal_evidence, *, required_usable=4, window_size=6):
    if not isinstance(temporal_evidence, dict):
        return {
            "status": "INSUFFICIENT",
            "usable_observations": 0,
            "window_size": window_size,
            "required_usable": required_usable,
            "reason": "Temporal evidence was not supplied",
        }
    association = temporal_evidence.get("identity_association") or {}
    if association.get("identity_status") == IDENTITY_TEMPORAL_VALID:
        compound = association.get("compound_observation") or {}
        return {
            "status": IDENTITY_TEMPORAL_VALID,
            "usable_observations": association.get("historical_core", {}).get("observation_count", 0),
            "window_size": window_size,
            "required_usable": required_usable,
            "persistent_track_count": 1,
            "compound_component_count": compound.get("component_count", 1),
            "reason": "Existing temporal tracker and identity association support one persistent historical core",
        }
    usable_ids = temporal_evidence.get("usable_observation_ids") or []
    observations = temporal_evidence.get("observations") or []
    usable_count = len(set(usable_ids))
    if not usable_count:
        usable_count = sum(
            1 for observation in observations
            if observation.get("temporal_evidence_status") == "USABLE"
        )
    tracks = temporal_evidence.get("tracks") or []
    persistent_tracks = [
        track for track in tracks
        if track.get("observation_count", 0) >= 3
    ]
    accepted = (
        usable_count >= required_usable
        and usable_count <= window_size
        and len(persistent_tracks) == 1
    )
    return {
        "status": IDENTITY_TEMPORAL_VALID if accepted else "INSUFFICIENT",
        "usable_observations": usable_count,
        "window_size": window_size,
        "required_usable": required_usable,
        "persistent_track_count": len(persistent_tracks),
        "reason": (
            "At least four usable observations in the latest six support one persistent track"
            if accepted
            else "Temporal evidence does not meet the usable-observation and unique-track requirements"
        ),
    }


def _spatial_signal(candidate_detection):
    detection = candidate_detection or {}
    selected = detection.get("selected_candidate") or {}
    candidates = detection.get("candidates") or []
    evidence = selected.get("evidence") or {}
    competing = [candidate for candidate in candidates if candidate is not selected]
    conflict = bool(competing and evidence.get("score_gap_to_next_candidate", 1) < 0.15)
    valid_fraction = selected.get("valid_pixel_fraction", evidence.get("valid_pixel_fraction"))
    quality_ok = not isinstance(valid_fraction, (int, float)) or valid_fraction >= 0.6
    status = "CONSISTENT" if selected and not conflict and quality_ok else "CONFLICTING"
    reasons = []
    if conflict:
        reasons.append("Competing candidates have insufficient evidence separation")
    if not quality_ok:
        reasons.append("Selected candidate valid-pixel context is below the existing threshold")
    if not selected:
        reasons.append("No selected candidate is available")
    return {
        "status": status,
        "candidate_id": selected.get("candidate_id"),
        "centroid": deepcopy(selected.get("centroid")),
        "area_sqkm": selected.get("area_sqkm"),
        "valid_pixel_fraction": valid_fraction,
        "competing_candidate_count": len(competing),
        "boundary_consistency": deepcopy(selected.get("evidence", {}).get("boundary_consistency")),
        "reasons": reasons or ["Candidate location, shape, quality context, and competition are consistent"],
    }


def _reference_signal(authoritative_validation):
    validation = authoritative_validation or {}
    status = validation.get("identity_status")
    if status == IDENTITY_SUPPORTED and validation.get("measurement_authority") == "AUTHORITATIVE_REFERENCE_VALIDATED":
        return {
            "status": "TRUSTED_REFERENCE_VALIDATED",
            "trust": validation.get("reference_geometry_trust"),
            "spatial_validation": deepcopy(validation.get("spatial_validation")),
            "temporal_validation": deepcopy(validation.get("temporal_validation")),
            "reason": "Trusted reference validation supports the candidate",
        }
    return {
        "status": "UNAVAILABLE_OR_UNTRUSTED",
        "trust": validation.get("reference_geometry_trust", "UNTRUSTED"),
        "spatial_validation": deepcopy(validation.get("spatial_validation")),
        "temporal_validation": deepcopy(validation.get("temporal_validation")),
        "reason": "No trusted reference validation supports authoritative identity",
    }


def evaluate_multi_signal_identity(
    *,
    candidate_detection=None,
    temporal_evidence=None,
    satellite_cross_validation=None,
    authoritative_validation=None,
    primary_provenance=None,
    required_usable_observations=4,
    temporal_window_size=6,
):
    """Combine existing identity evidence without calculating area or risk."""
    temporal = _temporal_signal(
        temporal_evidence,
        required_usable=required_usable_observations,
        window_size=temporal_window_size,
    )
    spatial = _spatial_signal(candidate_detection)
    reference = _reference_signal(authoritative_validation)
    corroboration = satellite_cross_validation or {}
    satellite_status = corroboration.get("status", NO_INDEPENDENT_DATA)

    supporting = []
    conflicting = []
    unavailable = []
    if temporal["status"] == IDENTITY_TEMPORAL_VALID:
        supporting.append("temporal persistence")
    else:
        unavailable.append("sufficient temporal persistence")
    if satellite_status == SATELLITES_AGREE:
        supporting.append("independent satellite agreement")
    elif satellite_status == SATELLITES_DISAGREE:
        conflicting.append("independent satellite disagreement")
    else:
        unavailable.append("independent satellite corroboration")
    if spatial["status"] == "CONSISTENT":
        supporting.append("spatial/object consistency")
    else:
        conflicting.extend(spatial["reasons"])
    if reference["status"] == "TRUSTED_REFERENCE_VALIDATED":
        supporting.append("trusted reference validation")
    else:
        unavailable.append("trusted reference geometry validation")

    identity_status = IDENTITY_AMBIGUOUS
    confidence = "INSUFFICIENT"
    measurement_permitted = False
    reasons = []
    if conflicting:
        confidence = "LOW"
        reasons.append("Conflicting identity evidence prevents a supported identity decision")
    elif (
        temporal["status"] == IDENTITY_TEMPORAL_VALID
        and spatial["status"] == "CONSISTENT"
        and reference["status"] == "TRUSTED_REFERENCE_VALIDATED"
        and satellite_status in {SATELLITES_AGREE, NO_INDEPENDENT_DATA}
    ):
        identity_status = IDENTITY_SUPPORTED
        confidence = "HIGH" if satellite_status == SATELLITES_AGREE else "MODERATE"
        measurement_permitted = True
        reasons.append("Multiple independent signals support one target candidate")
    else:
        reasons.append("Required independent identity signals are missing or insufficient")

    return {
        "identity_status": identity_status,
        "confidence": confidence,
        "measurement_permitted": measurement_permitted,
        "supporting_signals": supporting,
        "conflicting_signals": conflicting,
        "unavailable_signals": unavailable,
        "evidence_counts": {
            "temporal_usable_observations": temporal["usable_observations"],
            "temporal_window_size": temporal["window_size"],
            "persistent_tracks": temporal.get("persistent_track_count", 0),
            "competing_candidates": spatial["competing_candidate_count"],
        },
        "spatial_metrics": spatial,
        "temporal_evidence": temporal,
        "satellite_cross_validation": deepcopy(corroboration),
        "authoritative_reference": reference,
        "reason": reasons,
        "provenance": deepcopy(primary_provenance) or {
            "type": "DERIVED_FROM_REAL_DATA",
            "method": "Multi-signal identity evaluation",
        },
        "limitations": [
            "Identity support is not proof of a GLOF event or probability",
            "Temporal persistence and satellite agreement cannot replace a trusted reference geometry",
        ],
        "explanation": "; ".join(reasons),
    }