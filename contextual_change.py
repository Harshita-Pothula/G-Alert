"""Contextual satellite change evidence built on the seasonal baseline."""

from copy import deepcopy


CHANGE_EVIDENCE_ESTABLISHED = "CHANGE_EVIDENCE_ESTABLISHED"
CHANGE_NOT_ESTABLISHED = "CHANGE_NOT_ESTABLISHED"
CHANGE_EVIDENCE_INSUFFICIENT = "CHANGE_EVIDENCE_INSUFFICIENT"


def _boundaries(observation):
    candidate = observation.get("candidate_detection") or {}
    selected = candidate.get("selected_candidate") or {}
    boundary = selected.get("boundary") or observation.get("boundary")
    return boundary


def _quality_assessment(current_observation, seasonal_comparison):
    quality = current_observation.get("data_quality") or {}
    masking = current_observation.get("quality_masking") or {}
    cloud_cover = current_observation.get("cloud_cover_percent")
    reasons = []
    if masking.get("status") not in {None, "APPLIED"}:
        reasons.append("quality masking was not applied")
    if isinstance(cloud_cover, (int, float)) and cloud_cover >= 50:
        reasons.append("cloud cover is at or above the existing 50 percent quality concern level")
    if isinstance(quality.get("valid_pixel_fraction"), (int, float)) and quality["valid_pixel_fraction"] < 0.6:
        reasons.append("valid-pixel fraction is below the existing 0.6 identity context level")
    comparison_quality = (seasonal_comparison.get("baseline") or {}).get("provenance", {})
    if not quality:
        reasons.append("current data-quality information is unavailable")
    return {
        "status": "HIGH_UNCERTAINTY" if reasons else "QUALITY_CONTEXT_AVAILABLE",
        "confidence": quality.get("confidence"),
        "cloud_cover_percent": cloud_cover,
        "valid_pixel_fraction": quality.get("valid_pixel_fraction"),
        "reasons": reasons,
        "baseline_provenance": deepcopy(comparison_quality),
    }


def _temporal_assessment(temporal_evidence, seasonal_comparison):
    temporal = temporal_evidence or {}
    observations = (seasonal_comparison.get("baseline") or {}).get("observations") or []
    if not temporal:
        return {
            "status": "INSUFFICIENT",
            "observation_count": 0,
            "reason": "No explicit multi-acquisition temporal evidence was supplied",
        }
    eligible_ids = temporal.get("usable_observation_ids") or []
    tracks = temporal.get("tracks") or []
    supporting_tracks = [
        track for track in tracks
        if track.get("observation_count", 0) >= temporal.get("minimum_observations", 3)
    ]
    if temporal.get("identity_status") in {"IDENTITY_AMBIGUOUS", "IDENTITY_UNCERTAIN"}:
        return {
            "status": "CONFLICTING",
            "observation_count": len(eligible_ids),
            "reason": "Temporal evidence does not uniquely support one target track",
        }
    if not supporting_tracks:
        return {
            "status": "INSUFFICIENT",
            "observation_count": len(eligible_ids) or len(observations),
            "reason": "No temporally persistent eligible candidate track was supplied",
        }
    return {
        "status": "CONSISTENT",
        "observation_count": len(eligible_ids) or len(observations),
        "supporting_track_count": len(supporting_tracks),
        "reason": "At least one eligible candidate track is temporally persistent",
    }


def evaluate_contextual_change(
    current_observation,
    seasonal_comparison,
    *,
    temporal_evidence=None,
    identity_status=None,
):
    """Return contextual change evidence, never a risk score or GLOF probability."""
    if not isinstance(current_observation, dict) or not isinstance(seasonal_comparison, dict):
        return {
            "status": CHANGE_EVIDENCE_INSUFFICIENT,
            "reason": "Current observation or seasonal comparison is invalid",
            "change_magnitude": None,
            "uncertainty": {"level": "HIGH", "reasons": ["required evidence is invalid"]},
        }

    baseline = seasonal_comparison.get("baseline") or {}
    statistics = baseline.get("statistics") or {}
    current_area = seasonal_comparison.get("current_value")
    baseline_mean = seasonal_comparison.get("baseline_value", statistics.get("mean"))
    area_status = "INSUFFICIENT"
    area_deviation = None
    area_deviation_percentage = seasonal_comparison.get("deviation_percentage")
    if seasonal_comparison.get("status") == "VALID" and isinstance(current_area, (int, float)) and isinstance(baseline_mean, (int, float)):
        area_deviation = current_area - baseline_mean
        area_status = (
            "EXPANSION_RELATIVE_TO_SEASONAL_BASELINE"
            if area_deviation > 0
            else "CONTRACTION_RELATIVE_TO_SEASONAL_BASELINE"
            if area_deviation < 0
            else "NO_AREA_DEVIATION"
        )

    historical_observations = baseline.get("observations") or []
    current_boundary = _boundaries(current_observation)
    boundary_records = [
        item.get("candidate_detection", {}).get("selected_candidate", {}).get("boundary")
        or item.get("boundary")
        for item in historical_observations
    ]
    boundary_records = [boundary for boundary in boundary_records if boundary]
    boundary_result = {
        "status": "INSUFFICIENT",
        "comparison_count": 0,
        "displacement_km": None,
        "reason": "Current or historical candidate boundaries are unavailable",
    }
    if current_boundary and boundary_records:
        try:
            from satellite.lake_detection import geometry_boundary_distance_km

            distances = [
                geometry_boundary_distance_km(current_boundary, boundary)
                for boundary in boundary_records
            ]
            distances = [distance for distance in distances if isinstance(distance, (int, float))]
            if distances:
                boundary_result = {
                    "status": "DISPLACEMENT_OBSERVED" if max(distances) > 0 else "NO_DISPLACEMENT_OBSERVED",
                    "comparison_count": len(distances),
                    "displacement_km": max(distances),
                    "reason": "Current boundary compared with historical candidate boundaries",
                }
        except (ImportError, TypeError, ValueError):
            boundary_result["reason"] = "Boundary geometry comparison was unavailable"

    temporal_result = _temporal_assessment(temporal_evidence, seasonal_comparison)
    quality_result = _quality_assessment(current_observation, seasonal_comparison)
    identity = identity_status or current_observation.get("identity_status")
    uncertainty_reasons = []
    if seasonal_comparison.get("status") != "VALID":
        uncertainty_reasons.append("seasonal baseline is insufficient or unavailable")
    if identity != "IDENTITY_SUPPORTED":
        uncertainty_reasons.append("lake identity is not explicitly supported")
    if boundary_result["status"] == "INSUFFICIENT":
        uncertainty_reasons.append(boundary_result["reason"])
    if temporal_result["status"] != "CONSISTENT":
        uncertainty_reasons.append(temporal_result["reason"])
    uncertainty_reasons.extend(quality_result["reasons"])

    if quality_result["status"] == "HIGH_UNCERTAINTY":
        uncertainty_level = "HIGH"
    elif uncertainty_reasons:
        uncertainty_level = "HIGH" if len(uncertainty_reasons) >= 2 else "MODERATE"
    else:
        uncertainty_level = "LOW"

    if area_status == "INSUFFICIENT":
        result_status = CHANGE_EVIDENCE_INSUFFICIENT
    elif uncertainty_level == "HIGH":
        result_status = CHANGE_NOT_ESTABLISHED
    else:
        result_status = CHANGE_EVIDENCE_ESTABLISHED

    return {
        "status": result_status,
        "interpretation": (
            "Contextual satellite change evidence only; lake expansion does not establish a GLOF event or probability."
        ),
        "change_magnitude": {
            "water_area_current_sqkm": current_area,
            "water_area_seasonal_baseline_mean_sqkm": baseline_mean,
            "water_area_deviation_sqkm": area_deviation,
            "water_area_deviation_percentage": area_deviation_percentage,
            "water_area_status": area_status,
            "boundary": boundary_result,
        },
        "evidence_dimensions": {
            "water_area": {"status": area_status, "deviation_percentage": area_deviation_percentage},
            "boundary_displacement": boundary_result,
            "temporal_consistency": temporal_result,
            "satellite_quality": quality_result,
        },
        "uncertainty": {
            "level": uncertainty_level,
            "reasons": uncertainty_reasons,
        },
        "seasonal_baseline": deepcopy(baseline),
        "provenance": deepcopy(current_observation.get("provenance"))
        or deepcopy((seasonal_comparison.get("provenance") or {})),
        "assumptions": deepcopy(current_observation.get("assumptions") or []),
        "limitations": deepcopy(current_observation.get("limitations") or []),
        "does_not_trigger_glof_warning": True,
    }