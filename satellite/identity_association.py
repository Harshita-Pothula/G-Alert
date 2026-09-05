"""Conservative association of fragmented candidates to historical lake cores."""

from copy import deepcopy
from statistics import median

from satellite.lake_detection import (
    geometry_boundary_distance_km,
    geometry_overlap_ratio,
    haversine_km,
)


IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"


IDENTITY_TEMPORAL_VALID = "IDENTITY_TEMPORAL_VALID"
CORE_MATCH_DISTANCE_KM = 1.0
COMPOUND_COMPONENT_DISTANCE_KM = 0.5
MIN_HISTORICAL_OBSERVATIONS = 3


def _candidate_usable(candidate):
    eligibility = candidate.get("temporal_eligibility")
    if isinstance(eligibility, dict) and not eligibility.get("eligible"):
        return False, eligibility.get("reasons") or ["candidate failed temporal eligibility"]
    evidence = candidate.get("evidence", {})
    valid_fraction = candidate.get("valid_pixel_fraction", evidence.get("valid_pixel_fraction"))
    if isinstance(valid_fraction, (int, float)) and valid_fraction < 0.6:
        return False, ["candidate valid-pixel fraction is below the existing 0.6 threshold"]
    if candidate.get("geometry_part_count", 1) > 1:
        return False, ["candidate geometry is fragmented into multiple polygon parts"]
    if not candidate.get("centroid"):
        return False, ["candidate centroid is unavailable"]
    return True, ["candidate quality and geometry context are usable"]


def _observation_candidates(observation):
    if not isinstance(observation, dict):
        return []
    if isinstance(observation.get("candidates"), list):
        return observation["candidates"]
    detection = observation.get("candidate_detection") or {}
    return detection.get("candidates") or []


def _historical_candidates(historical_observations):
    usable = []
    rejected = []
    for observation in historical_observations or []:
        image_id = observation.get("image_id")
        for candidate in _observation_candidates(observation):
            ok, reasons = _candidate_usable(candidate)
            if ok:
                usable.append({
                    "candidate": candidate,
                    "image_id": image_id,
                    "acquisition_time": observation.get("acquisition_time"),
                })
            else:
                rejected.append({
                    "image_id": image_id,
                    "candidate_id": candidate.get("candidate_id"),
                    "reasons": reasons,
                })
    return usable, rejected


def _cluster_historical(usable):
    clusters = []
    for item in usable:
        centroid = item["candidate"]["centroid"]
        matches = [
            cluster for cluster in clusters
            if haversine_km(cluster["centroid"], centroid) <= CORE_MATCH_DISTANCE_KM
        ]
        if matches:
            cluster = min(
                matches,
                key=lambda value: haversine_km(value["centroid"], centroid),
            )
            cluster["items"].append(item)
            cluster["centroid"] = {
                "longitude": median(item["candidate"]["centroid"]["longitude"] for item in cluster["items"]),
                "latitude": median(item["candidate"]["centroid"]["latitude"] for item in cluster["items"]),
            }
        else:
            clusters.append({"centroid": centroid, "items": [item]})
    return clusters


def _historical_core(cluster):
    items = cluster["items"]
    areas = [
        item["candidate"].get("area_sqkm")
        for item in items
        if isinstance(item["candidate"].get("area_sqkm"), (int, float))
    ]
    compactness = [
        item["candidate"].get("compactness")
        for item in items
        if isinstance(item["candidate"].get("compactness"), (int, float))
    ]
    ndwi = [
        item["candidate"].get("mean_ndwi")
        for item in items
        if isinstance(item["candidate"].get("mean_ndwi"), (int, float))
    ]
    return {
        "centroid": cluster["centroid"],
        "observation_count": len({item.get("image_id") for item in items}),
        "candidate_count": len(items),
        "area_median_sqkm": median(areas) if areas else None,
        "compactness_median": median(compactness) if compactness else None,
        "mean_ndwi_median": median(ndwi) if ndwi else None,
        "image_ids": [item.get("image_id") for item in items],
    }


def _component_evidence(candidate, core):
    centroid_distance = haversine_km(core["centroid"], candidate.get("centroid"))
    area = candidate.get("area_sqkm")
    area_ratio = None
    if isinstance(area, (int, float)) and isinstance(core.get("area_median_sqkm"), (int, float)) and core["area_median_sqkm"] > 0:
        area_ratio = area / core["area_median_sqkm"]
    compactness_delta = None
    if isinstance(candidate.get("compactness"), (int, float)) and isinstance(core.get("compactness_median"), (int, float)):
        compactness_delta = abs(candidate["compactness"] - core["compactness_median"])
    ndwi_delta = None
    if isinstance(candidate.get("mean_ndwi"), (int, float)) and isinstance(core.get("mean_ndwi_median"), (int, float)):
        ndwi_delta = abs(candidate["mean_ndwi"] - core["mean_ndwi_median"])
    return {
        "centroid_distance_km": centroid_distance,
        "area_ratio_to_historical_median": area_ratio,
        "compactness_delta": compactness_delta,
        "mean_ndwi_delta": ndwi_delta,
    }


def _compatible_components(first, second):
    first_boundary = first.get("boundary")
    second_boundary = second.get("boundary")
    centroid_distance = haversine_km(first.get("centroid"), second.get("centroid"))
    overlap = geometry_overlap_ratio(first_boundary, second_boundary)
    boundary_distance = geometry_boundary_distance_km(first_boundary, second_boundary)
    area_ratio = None
    if isinstance(first.get("area_sqkm"), (int, float)) and isinstance(second.get("area_sqkm"), (int, float)) and max(first["area_sqkm"], second["area_sqkm"]) > 0:
        area_ratio = min(first["area_sqkm"], second["area_sqkm"]) / max(first["area_sqkm"], second["area_sqkm"])
    compactness_delta = None
    if isinstance(first.get("compactness"), (int, float)) and isinstance(second.get("compactness"), (int, float)):
        compactness_delta = abs(first["compactness"] - second["compactness"])
    ndwi_delta = None
    if isinstance(first.get("mean_ndwi"), (int, float)) and isinstance(second.get("mean_ndwi"), (int, float)):
        ndwi_delta = abs(first["mean_ndwi"] - second["mean_ndwi"])
    accepted = (
        centroid_distance is not None
        and centroid_distance <= COMPOUND_COMPONENT_DISTANCE_KM
        and (overlap is not None and overlap >= 0.02 or boundary_distance is not None and boundary_distance <= 0.5)
        and (area_ratio is None or area_ratio >= 0.5)
        and (compactness_delta is None or compactness_delta <= 0.25)
        and (ndwi_delta is None or ndwi_delta <= 0.20)
    )
    return accepted, {
        "centroid_distance_km": centroid_distance,
        "overlap_ratio": overlap,
        "boundary_distance_km": boundary_distance,
        "area_ratio": area_ratio,
        "compactness_delta": compactness_delta,
        "mean_ndwi_delta": ndwi_delta,
        "reason": "components share spatial, area, shape, and spectral context" if accepted else "components are spatially or physically inconsistent",
    }


def _compound_geometry(candidates):
    boundaries = [candidate.get("boundary") for candidate in candidates if candidate.get("boundary")]
    if not boundaries:
        return None
    try:
        from shapely.geometry import mapping, shape
        from shapely.ops import unary_union

        return mapping(unary_union([shape(boundary) for boundary in boundaries]))
    except (ImportError, TypeError, ValueError):
        return None


def associate_temporal_identity(current_candidates: list, historical_observations: list) -> dict:
    """Associate current fragments to a historical core without proving identity."""
    usable, rejected = _historical_candidates(historical_observations)
    clusters = _cluster_historical(usable)
    cores = [_historical_core(cluster) for cluster in clusters]
    result = {
        "identity_status": IDENTITY_AMBIGUOUS,
        "measurement_permitted": False,
        "association_status": "INSUFFICIENT_EVIDENCE",
        "historical_core": None,
        "accepted_candidates": [],
        "rejected_candidates": rejected,
        "compound_observation": None,
        "association_decisions": [],
        "provenance": {
            "type": "DERIVED_FROM_REAL_DATA",
            "method": "Historical candidate-centroid and compound-component association",
            "limitations": [
                "Association is derived evidence and does not prove named-lake identity",
                "Authoritative reference and measurement gates remain external",
            ],
        },
    }
    if not cores:
        result["reason"] = ["No usable historical candidate centroids were available"]
        return result
    cores.sort(key=lambda core: core["observation_count"], reverse=True)
    if len(cores) > 1 and cores[0]["observation_count"] == cores[1]["observation_count"]:
        result["reason"] = ["Multiple historical candidate cores have equal persistence"]
        result["association_status"] = "AMBIGUOUS_HISTORICAL_CORES"
        result["historical_cores"] = cores
        return result
    core = cores[0]
    result["historical_core"] = core
    if core["observation_count"] < MIN_HISTORICAL_OBSERVATIONS:
        result["reason"] = [
            f"Historical core has only {core['observation_count']} usable observations; {MIN_HISTORICAL_OBSERVATIONS} are required"
        ]
        return result

    near = []
    for candidate in current_candidates or []:
        usable_candidate, reasons = _candidate_usable(candidate)
        evidence = _component_evidence(candidate, core)
        accepted = usable_candidate and evidence["centroid_distance_km"] is not None and evidence["centroid_distance_km"] <= CORE_MATCH_DISTANCE_KM
        decision = {
            "candidate_id": candidate.get("candidate_id"),
            "accepted_for_core": accepted,
            "evidence": evidence,
            "reasons": reasons if not usable_candidate else ([] if accepted else ["candidate is outside the historical trajectory/core proximity gate"]),
        }
        result["association_decisions"].append(decision)
        if accepted:
            near.append(candidate)
        else:
            result["rejected_candidates"].append(decision)
    if not near:
        result["reason"] = ["No current candidate lies within the historical trajectory/core proximity gate"]
        return result

    groups = [[near[0]]]
    for candidate in near[1:]:
        compatible = False
        for group in groups:
            matches = [_compatible_components(group_candidate, candidate) for group_candidate in group]
            if all(match[0] for match in matches):
                group.append(candidate)
                compatible = True
                break
        if not compatible:
            groups.append([candidate])
    if len(groups) > 1:
        result["association_status"] = "COMPETING_CURRENT_GROUPS"
        result["reason"] = ["Multiple current candidate groups remain spatially or physically distinct"]
        result["rejected_candidates"].extend({
            "candidate_id": candidate.get("candidate_id"),
            "reasons": ["candidate belongs to a competing current compound group"],
        } for group in groups[1:] for candidate in group)
        return result

    accepted = groups[0]
    result["accepted_candidates"] = deepcopy(accepted)
    result["compound_observation"] = {
        "component_count": len(accepted),
        "candidate_ids": [candidate.get("candidate_id") for candidate in accepted],
        "area_sqkm_sum": sum(
            candidate.get("area_sqkm", 0) for candidate in accepted
            if isinstance(candidate.get("area_sqkm"), (int, float))
        ),
        "geometry_union": _compound_geometry(accepted),
        "geometry_union_is_derived_evidence": True,
        "component_consistency": [
            _compatible_components(first, second)[1]
            for index, first in enumerate(accepted)
            for second in accepted[index + 1:]
        ],
    }
    result["association_status"] = "COMPOUND_ASSOCIATED" if len(accepted) > 1 else "SINGLE_ASSOCIATED"
    result["reason"] = [
        "Current candidate(s) associate with one persistent historical core; identity and authoritative measurement gates still apply"
    ]
    if core["observation_count"] >= MIN_HISTORICAL_OBSERVATIONS:
        result["identity_status"] = IDENTITY_TEMPORAL_VALID
    return result