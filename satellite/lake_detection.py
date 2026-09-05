"""Satellite-derived candidate water-body detection for one configured lake."""

from math import asin, cos, radians, sin, sqrt


IDENTITY_SUPPORTED = "IDENTITY_SUPPORTED"
IDENTITY_UNCERTAIN = "IDENTITY_UNCERTAIN"
IDENTITY_NOT_ESTABLISHED = "IDENTITY_NOT_ESTABLISHED"


def can_publish_observed_area(identity_status, area_result, boundary):
    """Allow a target area only after identity and measurement validity pass."""
    return (
        identity_status == IDENTITY_SUPPORTED
        and isinstance(area_result, dict)
        and area_result.get("status") == "SUCCESS"
        and isinstance(area_result.get("area_sqkm"), (int, float))
        and boundary is not None
    )


def _geometry_coordinates(geometry):
    """Yield coordinate pairs from a GeoJSON geometry recursively."""
    coordinates = geometry.get("coordinates", [])
    if geometry.get("type") == "Point":
        yield coordinates
        return
    for item in coordinates:
        if isinstance(item, (list, tuple)) and len(item) == 2 and all(
            isinstance(value, (int, float)) for value in item
        ):
            yield item
        elif isinstance(item, (list, tuple)):
            yield from _geometry_coordinates({"coordinates": item})


def geometry_center(geometry):
    """Return the arithmetic center of a GeoJSON geometry."""
    points = list(_geometry_coordinates(geometry))
    if not points:
        return None
    return {
        "longitude": sum(point[0] for point in points) / len(points),
        "latitude": sum(point[1] for point in points) / len(points),
    }


def haversine_km(first, second):
    """Return approximate distance between two longitude/latitude points."""
    if not first or not second:
        return None
    latitude_1 = radians(first["latitude"])
    latitude_2 = radians(second["latitude"])
    delta_latitude = radians(second["latitude"] - first["latitude"])
    delta_longitude = radians(second["longitude"] - first["longitude"])
    value = (
        sin(delta_latitude / 2) ** 2
        + cos(latitude_1) * cos(latitude_2) * sin(delta_longitude / 2) ** 2
    )
    return 6371.0 * 2 * asin(sqrt(value))


def candidate_boundary_proximity(candidate_bounds, roi_bounds, tolerance=0.05):
    """Report whether a candidate is close to the approximate ROI boundary."""
    if not candidate_bounds or not roi_bounds:
        return "UNKNOWN"
    candidate_width = candidate_bounds["max_longitude"] - candidate_bounds["min_longitude"]
    candidate_height = candidate_bounds["max_latitude"] - candidate_bounds["min_latitude"]
    roi_width = roi_bounds["max_longitude"] - roi_bounds["min_longitude"]
    roi_height = roi_bounds["max_latitude"] - roi_bounds["min_latitude"]
    longitude_margin = max(roi_width * tolerance, candidate_width * 0.1)
    latitude_margin = max(roi_height * tolerance, candidate_height * 0.1)
    touches = (
        candidate_bounds["min_longitude"] <= roi_bounds["min_longitude"] + longitude_margin
        or candidate_bounds["max_longitude"] >= roi_bounds["max_longitude"] - longitude_margin
        or candidate_bounds["min_latitude"] <= roi_bounds["min_latitude"] + latitude_margin
        or candidate_bounds["max_latitude"] >= roi_bounds["max_latitude"] - latitude_margin
    )
    return "HIGH" if touches else "LOW"


def _plausible_area(area_sqkm):
    """Use a broad lake-scale screening range, not a claimed lake area."""
    return isinstance(area_sqkm, (int, float)) and 0.1 <= area_sqkm <= 10.0


def _shape_context(candidate):
    """Describe elongated geometry as evidence, without classifying it as a river."""
    bounds = candidate.get("bounds") or {}
    width = bounds.get("max_longitude", 0) - bounds.get("min_longitude", 0)
    height = bounds.get("max_latitude", 0) - bounds.get("min_latitude", 0)
    if width <= 0 or height <= 0:
        return "UNAVAILABLE"
    aspect_ratio = max(width, height) / min(width, height)
    compactness = candidate.get("compactness")
    if aspect_ratio >= 5 and isinstance(compactness, (int, float)) and compactness < 0.02:
        return "POSSIBLE_LINEAR_WATER_FEATURE"
    return "NOT_OBVIOUSLY_LINEAR"


def assess_lake_likeness(candidates, temporal_evidence=None):
    """Summarize lake-like evidence without asserting named identity."""
    candidates = candidates or []
    tracks = (temporal_evidence or {}).get("tracks", [])
    persistent_tracks = [
        track for track in tracks
        if track.get("observation_count", 0) >= 3
    ]
    evidence = []
    conflicts = []
    for candidate in candidates:
        candidate_evidence = candidate.get("evidence", {})
        spectral = candidate.get("spectral_context", {})
        terrain = candidate.get("terrain_context", {})
        shape_context = candidate_evidence.get("shape_context") or _shape_context(candidate)
        if shape_context == "POSSIBLE_LINEAR_WATER_FEATURE":
            conflicts.append("candidate geometry is potentially linear water")
        if candidate_evidence.get("spectral_water_support"):
            evidence.append("positive NDWI water support")
        if isinstance(spectral.get("mndwi"), (int, float)):
            evidence.append("real Sentinel-2 Green/SWIR context available")
        if isinstance(terrain.get("elevation_m"), (int, float)):
            evidence.append("real DEM elevation context available")
        if isinstance(terrain.get("slope_degrees"), (int, float)):
            evidence.append("real DEM slope context available")
        if shape_context == "NOT_OBVIOUSLY_LINEAR":
            evidence.append("candidate is not obviously linear from geometry")
    if len(persistent_tracks) == 1:
        evidence.append("one persistent temporal track")
    elif len(persistent_tracks) > 1:
        conflicts.append("multiple persistent temporal tracks remain")
    if conflicts:
        status = "CONFLICTING"
    elif evidence:
        status = "SUPPORTING" if len(evidence) >= 2 else "INSUFFICIENT"
    else:
        status = "INSUFFICIENT"
    return {
        "status": status,
        "evidence": evidence,
        "conflicts": conflicts,
        "persistent_track_count": len(persistent_tracks),
        "interpretation": "Lake-like evidence is derived context, not named-lake identity or measurement authority",
    }


def deduplicate_candidates(candidates, *, min_overlap_ratio=0.02, max_centroid_distance_km=1.0):
    """Collapse only geometrically compatible cross-tile duplicates."""
    unique = []
    duplicates = []
    for candidate in candidates or []:
        matching = []
        for existing in unique:
            distance = haversine_km(existing.get("centroid"), candidate.get("centroid"))
            overlap = geometry_overlap_ratio(existing.get("boundary"), candidate.get("boundary"))
            if (
                distance is not None
                and distance <= max_centroid_distance_km
                and overlap is not None
                and overlap >= min_overlap_ratio
            ):
                matching.append((existing, distance, overlap))
        if matching:
            existing, distance, overlap = max(matching, key=lambda item: item[2])
            duplicates.append({
                "duplicate_candidate_id": candidate.get("candidate_id"),
                "retained_candidate_id": existing.get("candidate_id"),
                "centroid_distance_km": distance,
                "overlap_ratio": overlap,
                "reason": "Cross-tile candidates passed existing spatial compatibility evidence",
            })
            existing.setdefault("source_candidate_ids", []).append(candidate.get("candidate_id"))
        else:
            retained = dict(candidate)
            retained.setdefault("source_candidate_ids", [candidate.get("candidate_id")])
            unique.append(retained)
    return {"candidates": unique, "duplicates": duplicates}


def score_candidate(candidate, expected_center, roi_bounds, ndwi_threshold, valid_pixel_fraction):
    """Score evidence for candidate identity; this is not a probability."""
    distance = haversine_km(expected_center, candidate.get("centroid"))
    proximity = candidate_boundary_proximity(candidate.get("bounds"), roi_bounds)
    area_plausible = _plausible_area(candidate.get("area_sqkm"))
    ndwi_mean = candidate.get("mean_ndwi")
    spectral_support = isinstance(ndwi_mean, (int, float)) and ndwi_mean >= ndwi_threshold + 0.05
    compactness = candidate.get("compactness")
    shape_support = isinstance(compactness, (int, float)) and compactness >= 0.02
    shape_context = _shape_context(candidate)

    score = 0.0
    if distance is not None and distance <= 3.0:
        score += 0.35
    elif distance is not None and distance <= 6.0:
        score += 0.15
    if proximity == "LOW":
        score += 0.20
    if area_plausible:
        score += 0.15
    if spectral_support:
        score += 0.15
    if shape_support:
        score += 0.15

    candidate_valid_fraction = candidate.get("valid_pixel_fraction", valid_pixel_fraction)
    candidate["evidence"] = {
        "distance_to_expected_center_km": round(distance, 3) if distance is not None else None,
        "boundary_proximity": proximity,
        "area_plausible_under_broad_screen": area_plausible,
        "spectral_water_support": spectral_support,
        "shape_support": shape_support,
        "reference_overlap": "UNAVAILABLE",
        "temporal_persistence": "NOT_ASSESSED",
        "river_like_shape": shape_context,
        "shape_context": shape_context,
        "valid_pixel_fraction": candidate_valid_fraction,
        "mean_ndwi": ndwi_mean,
        "compactness": compactness,
        "evidence_score": round(score, 4),
        "score_interpretation": "Heuristic ranking only; not a probability or validation result",
    }
    supporting = []
    contradictions = []
    if distance is not None and distance <= 3.0:
        supporting.append("candidate centroid is near the expected target location")
    if proximity == "LOW":
        supporting.append("candidate is not close to the ROI boundary")
    if area_plausible:
        supporting.append("candidate area passes the broad lake-scale screen")
    if spectral_support:
        supporting.append("candidate has positive NDWI spectral support")
    if shape_support:
        supporting.append("candidate geometry has non-zero compactness support")
    if distance is None or distance > 6:
        contradictions.append("candidate is distant from the expected target location")
    if proximity == "HIGH":
        contradictions.append("candidate may be truncated by the ROI boundary")
    if not area_plausible:
        contradictions.append("candidate area fails the broad lake-scale screen")
    if not spectral_support:
        contradictions.append("candidate mean NDWI is weak")
    if shape_context == "POSSIBLE_LINEAR_WATER_FEATURE":
        contradictions.append("candidate geometry is an elongated, low-compactness water feature")
    if candidate.get("geometry_part_count", 0) > 1:
        contradictions.append("candidate boundary is fragmented into multiple parts")
    candidate["evidence"]["supporting_evidence"] = supporting
    candidate["evidence"]["contradictory_evidence"] = contradictions
    return candidate


def select_candidate(candidates, expected_center, roi_bounds, ndwi_threshold, valid_pixel_fraction, target_name="target lake"):
    """Select a candidate only when evidence is sufficiently specific."""
    if not candidates:
        return {
            "identity_status": IDENTITY_NOT_ESTABLISHED,
            "selected_candidate": None,
            "candidates": [],
            "reason": ["No connected water candidate met the minimum component filter"],
        }

    ranked = sorted(
        (
            score_candidate(
                candidate, expected_center, roi_bounds, ndwi_threshold, valid_pixel_fraction
            )
            for candidate in candidates
        ),
        key=lambda candidate: candidate["evidence"]["evidence_score"],
        reverse=True,
    )
    selected = ranked[0]
    selected_score = selected["evidence"]["evidence_score"]
    runner_up_score = ranked[1]["evidence"]["evidence_score"] if len(ranked) > 1 else 0.0
    score_gap = selected_score - runner_up_score
    evidence = selected["evidence"]
    reasons = []
    if evidence["distance_to_expected_center_km"] is None or evidence["distance_to_expected_center_km"] > 6:
        reasons.append(f"Candidate is not sufficiently close to the expected {target_name} location")
    if evidence["boundary_proximity"] != "LOW":
        reasons.append("Candidate is too close to the search ROI boundary")
    if not evidence["spectral_water_support"]:
        reasons.append("Spectral water evidence is not sufficiently strong")
    if len(ranked) > 1 and score_gap < 0.15:
        reasons.append("Competing water candidates have similar evidence scores")
    selected_valid_fraction = evidence["valid_pixel_fraction"]
    if selected_valid_fraction is not None and selected_valid_fraction < 0.6:
        reasons.append("Valid-pixel coverage is below the identity-support threshold")

    supported = (
        selected_score >= 0.7
        and score_gap >= 0.15
        and not reasons
    )
    identity_status = IDENTITY_SUPPORTED if supported else IDENTITY_UNCERTAIN
    if not supported and not reasons:
        reasons.append("Evidence is plausible but below the supported-identity threshold")

    selected["evidence"]["score_gap_to_next_candidate"] = round(score_gap, 4)
    return {
        "identity_status": identity_status,
        "selected_candidate": selected,
        "candidates": ranked,
        "reason": reasons,
    }


def _mean_center(points):
    points = list(points)
    if not points:
        return None
    return {
        "longitude": sum(point["longitude"] for point in points) / len(points),
        "latitude": sum(point["latitude"] for point in points) / len(points),
    }


def geometry_overlap_ratio(first_geometry, second_geometry):
    """Return polygon IoU when Shapely is available, otherwise unknown."""
    if not first_geometry or not second_geometry:
        return None
    try:
        from shapely.geometry import shape

        first = shape(first_geometry)
        second = shape(second_geometry)
        union_area = first.union(second).area
        return first.intersection(second).area / union_area if union_area else 0.0
    except (ImportError, TypeError, ValueError):
        return None


def geometry_boundary_distance_km(first_geometry, second_geometry):
    """Approximate boundary distance using local longitude/latitude scaling."""
    if not first_geometry or not second_geometry:
        return None
    try:
        from shapely.geometry import shape

        first = shape(first_geometry)
        second = shape(second_geometry)
        latitude = (first.centroid.y + second.centroid.y) / 2
        longitude_km = 111.32 * cos(radians(latitude))
        latitude_km = 111.32
        return sqrt((first.distance(second) * longitude_km) ** 2 + (first.distance(second) * latitude_km) ** 2)
    except (ImportError, TypeError, ValueError):
        return None


def candidate_temporal_eligibility(candidate):
    """Exclude candidates whose local context is too degraded for persistence."""
    evidence = candidate.get("evidence", {})
    valid_fraction = evidence.get("valid_pixel_fraction")
    quality = candidate.get("quality", {})
    reasons = []
    if valid_fraction is None:
        reasons.append("candidate context valid-pixel fraction is unavailable")
    if isinstance(valid_fraction, (int, float)) and valid_fraction < 0.6:
        reasons.append("candidate context valid-pixel fraction is below 0.6")
    for key in ("cloud_shadow_fraction", "cloud_medium_fraction", "cloud_high_fraction", "cirrus_fraction", "snow_ice_fraction"):
        value = quality.get(key)
        if isinstance(value, (int, float)) and value > 0.4:
            reasons.append(f"candidate context {key} exceeds 0.4")
    if candidate.get("geometry_part_count", 1) > 1:
        reasons.append("candidate geometry is fragmented into multiple polygon parts")
    return {
        "eligible": not reasons,
        "reasons": reasons or ["candidate context quality is sufficient for temporal evidence"],
    }


def _candidate_match_evidence(track, candidate, max_match_distance_km, min_overlap_ratio, max_boundary_distance_km):
    """Score an existing spatial match using existing gates plus evidence context."""
    centroid_distance = haversine_km(track["centroid"], candidate.get("centroid"))
    overlap = geometry_overlap_ratio(track.get("boundary"), candidate.get("boundary"))
    boundary_distance = geometry_boundary_distance_km(
        track.get("boundary"), candidate.get("boundary")
    )
    area_values = [
        item.get("area_sqkm") for item in track.get("observations", [])
        if isinstance(item.get("area_sqkm"), (int, float))
    ]
    candidate_area = candidate.get("area_sqkm")
    area_ratio = None
    if area_values and isinstance(candidate_area, (int, float)) and max(area_values) > 0:
        area_ratio = candidate_area / (sum(area_values) / len(area_values))
    shape_values = [
        item.get("evidence", {}).get("compactness")
        for item in track.get("observations", [])
        if isinstance(item.get("evidence", {}).get("compactness"), (int, float))
    ]
    candidate_shape = candidate.get("compactness")
    shape_delta = None
    if shape_values and isinstance(candidate_shape, (int, float)):
        shape_delta = abs(candidate_shape - (sum(shape_values) / len(shape_values)))
    ndwi_values = [
        item.get("evidence", {}).get("mean_ndwi")
        for item in track.get("observations", [])
        if isinstance(item.get("evidence", {}).get("mean_ndwi"), (int, float))
    ]
    candidate_ndwi = candidate.get("mean_ndwi")
    ndwi_delta = None
    if ndwi_values and isinstance(candidate_ndwi, (int, float)):
        ndwi_delta = abs(candidate_ndwi - (sum(ndwi_values) / len(ndwi_values)))
    spatial_gate = (
        centroid_distance is not None
        and centroid_distance <= max_match_distance_km
        and (
            overlap is None
            or overlap >= min_overlap_ratio
            or (
                boundary_distance is not None
                and boundary_distance <= max_boundary_distance_km
            )
        )
    )
    evidence_score = 0.0
    evidence_score += 1.0 if overlap is not None and overlap >= min_overlap_ratio else 0.0
    evidence_score += 1.0 if boundary_distance is not None and boundary_distance <= max_boundary_distance_km else 0.0
    evidence_score += 1.0 if area_ratio is not None and 0.5 <= area_ratio <= 2.0 else 0.0
    evidence_score += 1.0 if shape_delta is not None and shape_delta <= 0.25 else 0.0
    evidence_score += 1.0 if ndwi_delta is not None and ndwi_delta <= 0.20 else 0.0
    return {
        "accepted": spatial_gate,
        "centroid_distance_km": centroid_distance,
        "overlap_ratio": overlap,
        "boundary_distance_km": boundary_distance,
        "area_ratio_to_track_mean": area_ratio,
        "compactness_delta": shape_delta,
        "mean_ndwi_delta": ndwi_delta,
        "evidence_score": evidence_score,
        "reasons": [] if spatial_gate else [
            "candidate failed existing centroid/overlap/boundary association gate"
        ],
    }


def _same_observation_component_evidence(first, second):
    """Apply the existing conservative component compatibility rules."""
    centroid_distance = haversine_km(first.get("centroid"), second.get("centroid"))
    overlap = geometry_overlap_ratio(first.get("boundary"), second.get("boundary"))
    boundary_distance = geometry_boundary_distance_km(
        first.get("boundary"), second.get("boundary")
    )
    area_ratio = None
    if (
        isinstance(first.get("area_sqkm"), (int, float))
        and isinstance(second.get("area_sqkm"), (int, float))
        and max(first["area_sqkm"], second["area_sqkm"]) > 0
    ):
        area_ratio = min(first["area_sqkm"], second["area_sqkm"]) / max(
            first["area_sqkm"], second["area_sqkm"]
        )
    compactness_delta = None
    if isinstance(first.get("compactness"), (int, float)) and isinstance(
        second.get("compactness"), (int, float)
    ):
        compactness_delta = abs(first["compactness"] - second["compactness"])
    ndwi_delta = None
    if isinstance(first.get("mean_ndwi"), (int, float)) and isinstance(
        second.get("mean_ndwi"), (int, float)
    ):
        ndwi_delta = abs(first["mean_ndwi"] - second["mean_ndwi"])
    accepted = (
        centroid_distance is not None
        and centroid_distance <= 0.5
        and (
            (overlap is not None and overlap >= 0.02)
            or (boundary_distance is not None and boundary_distance <= 0.5)
        )
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
        "reason": (
            "components share existing spatial, area, shape, and spectral compatibility"
            if accepted
            else "components are spatially or physically inconsistent"
        ),
    }


def _compound_candidate(groups):
    """Create derived tracking evidence from already-compatible components."""
    candidates = [candidate for candidate in groups]
    boundaries = [candidate.get("boundary") for candidate in candidates if candidate.get("boundary")]
    geometry_union = None
    if boundaries:
        try:
            from shapely.geometry import mapping, shape
            from shapely.ops import unary_union

            geometry_union = mapping(unary_union([shape(boundary) for boundary in boundaries]))
        except (ImportError, TypeError, ValueError):
            geometry_union = None
    areas = [
        candidate.get("area_sqkm") for candidate in candidates
        if isinstance(candidate.get("area_sqkm"), (int, float))
    ]
    centroids = [candidate.get("centroid") for candidate in candidates if candidate.get("centroid")]
    ndwi_values = [
        candidate.get("mean_ndwi") for candidate in candidates
        if isinstance(candidate.get("mean_ndwi"), (int, float))
    ]
    compactness_values = [
        candidate.get("compactness") for candidate in candidates
        if isinstance(candidate.get("compactness"), (int, float))
    ]
    valid_values = [
        candidate.get("valid_pixel_fraction")
        for candidate in candidates
        if isinstance(candidate.get("valid_pixel_fraction"), (int, float))
    ]
    return {
        "candidate_id": "compound_" + "_".join(
            str(candidate.get("candidate_id")) for candidate in candidates
        ),
        "boundary": geometry_union,
        "area_sqkm": sum(areas) if areas else None,
        "centroid": _mean_center(centroids),
        "mean_ndwi": sum(ndwi_values) / len(ndwi_values) if ndwi_values else None,
        "compactness": (
            sum(compactness_values) / len(compactness_values)
            if compactness_values else None
        ),
        "geometry_part_count": 1,
        "valid_pixel_fraction": min(valid_values) if valid_values else None,
        "evidence": {
            "valid_pixel_fraction": min(valid_values) if valid_values else None,
            "compactness": sum(compactness_values) / len(compactness_values)
            if compactness_values else None,
            "mean_ndwi": sum(ndwi_values) / len(ndwi_values) if ndwi_values else None,
            "compound_component_count": len(candidates),
            "compound_component_ids": [candidate.get("candidate_id") for candidate in candidates],
        },
        "quality": {
            "valid_pixel_fraction": min(valid_values) if valid_values else None,
        },
        "derived_compound": True,
        "compound_components": candidates,
    }


def _build_compound_tracking_candidates(candidates):
    """Group only mutually compatible eligible components for tracking."""
    eligible = [
        candidate for candidate in candidates
        if candidate.get("temporal_eligibility", {}).get("eligible")
        and candidate.get("centroid")
    ]
    groups = []
    used = set()
    for index, candidate in enumerate(eligible):
        if index in used:
            continue
        group = [candidate]
        used.add(index)
        for other_index, other in enumerate(eligible):
            if other_index in used:
                continue
            matches = [_same_observation_component_evidence(member, other) for member in group]
            if all(match[0] for match in matches):
                group.append(other)
                used.add(other_index)
        groups.append(group)
    compound_observations = [
        _compound_candidate(group)
        for group in groups
        if len(group) > 1 and _compound_candidate(group).get("boundary")
    ]
    compound_ids = {
        candidate.get("candidate_id")
        for compound in compound_observations
        for candidate in compound["compound_components"]
    }
    tracking_candidates = [
        candidate for candidate in candidates
        if candidate.get("candidate_id") not in compound_ids
    ] + compound_observations
    return tracking_candidates, compound_observations


def build_temporal_tracks(observations, max_match_distance_km=1.0, min_overlap_ratio=0.02, max_boundary_distance_km=0.5):
    """Associate candidates with one candidate per track per acquisition."""
    tracks = []
    excluded_candidates = []
    usable_observation_ids = []
    degraded_observations = []
    rejected_associations = []
    compound_observations = []
    for observation_index, observation in enumerate(observations):
        observation_candidates = observation.get("candidates", [])
        tracking_candidates, compounds = _build_compound_tracking_candidates(observation_candidates)
        compound_observations.extend({
            "image_id": observation.get("image_id"),
            "acquisition_time": observation.get("acquisition_time"),
            "candidate_id": compound.get("candidate_id"),
            "component_ids": [
                component.get("candidate_id")
                for component in compound.get("compound_components", [])
            ],
            "evidence": [
                _same_observation_component_evidence(first, second)[1]
                for index, first in enumerate(compound.get("compound_components", []))
                for second in compound.get("compound_components", [])[index + 1:]
            ],
        } for compound in compounds)
        observation_eligible = False
        matched_track_ids = set()
        for candidate in tracking_candidates:
            eligibility = candidate_temporal_eligibility(candidate)
            candidate["temporal_eligibility"] = eligibility
            if not eligibility["eligible"]:
                excluded_candidates.append({
                    "image_id": observation.get("image_id"),
                    "acquisition_time": observation.get("acquisition_time"),
                    "candidate_id": candidate.get("candidate_id"),
                    "reasons": eligibility["reasons"],
                })
                continue
            observation_eligible = True
            centroid = candidate.get("centroid")
            if not centroid:
                continue
            matches = [
                (
                    _candidate_match_evidence(
                        track, candidate, max_match_distance_km,
                        min_overlap_ratio, max_boundary_distance_km,
                    ),
                    track,
                )
                for track in tracks
                if track.get("track_id") not in matched_track_ids
                if haversine_km(track["centroid"], centroid) is not None
                and haversine_km(track["centroid"], centroid) <= max_match_distance_km
                and _candidate_match_evidence(
                    track, candidate, max_match_distance_km,
                    min_overlap_ratio, max_boundary_distance_km,
                )["accepted"]
            ]
            if matches:
                match_evidence, track = max(
                    matches, key=lambda item: item[0]["evidence_score"]
                )
                matched_track_ids.add(track["track_id"])
                candidate["temporal_match_evidence"] = match_evidence
            else:
                rejected_associations.append({
                    "image_id": observation.get("image_id"),
                    "candidate_id": candidate.get("candidate_id"),
                    "reason": "No existing track passed the spatial association gate or track already had a candidate for this acquisition",
                })
                track = {
                    "track_id": f"track_{len(tracks) + 1}",
                    "centroid": centroid,
                    "boundary": candidate.get("boundary"),
                    "observations": [],
                }
                tracks.append(track)
                matched_track_ids.add(track["track_id"])
                candidate["temporal_match_evidence"] = {
                    "accepted": True,
                    "new_track": True,
                    "evidence_score": 0.0,
                    "reasons": ["No prior compatible track; candidate starts a new track"],
                }
            track["observations"].append({
                "observation_index": observation_index,
                "image_id": observation.get("image_id"),
                "acquisition_time": observation.get("acquisition_time"),
                "candidate_id": candidate.get("candidate_id"),
                "area_sqkm": candidate.get("area_sqkm"),
                "centroid": centroid,
                "boundary": candidate.get("boundary"),
                "evidence": candidate.get("evidence", {}),
            })
            track["centroid"] = _mean_center(
                item["centroid"] for item in track["observations"]
            )
        if observation_eligible:
            usable_observation_ids.append(observation.get("image_id"))
        elif observation_candidates:
            degraded_observations.append({
                "image_id": observation.get("image_id"),
                "acquisition_time": observation.get("acquisition_time"),
                "reason": "All candidates were excluded from temporal evidence",
            })
        elif observation.get("status") not in {None, "SUCCESS", "QUALITY_APPLIED"}:
            degraded_observations.append({
                "image_id": observation.get("image_id"),
                "acquisition_time": observation.get("acquisition_time"),
                "reason": observation.get("reason") or observation.get("status"),
            })

    for track in tracks:
        areas = [
            item["area_sqkm"] for item in track["observations"]
            if isinstance(item.get("area_sqkm"), (int, float))
        ]
        distances = [
            haversine_km(track["centroid"], item["centroid"])
            for item in track["observations"]
        ]
        observation_ids = {
            item.get("image_id") for item in track["observations"]
            if item.get("image_id") is not None
        }
        track["observation_count"] = len(observation_ids)
        track["candidate_observation_count"] = len(track["observations"])
        track["area_summary"] = {
            "min_sqkm": min(areas) if areas else None,
            "max_sqkm": max(areas) if areas else None,
            "range_sqkm": max(areas) - min(areas) if areas else None,
            "area_is_not_averaged": True,
        }
        track["spatial_consistency"] = {
            "maximum_centroid_deviation_km": max(distances) if distances else None,
            "match_distance_threshold_km": max_match_distance_km,
            "minimum_overlap_ratio": min_overlap_ratio,
            "maximum_boundary_distance_km": max_boundary_distance_km,
        }
        overlaps = []
        boundary_distances = []
        for previous, current in zip(track["observations"], track["observations"][1:]):
            overlap = geometry_overlap_ratio(previous.get("boundary"), current.get("boundary"))
            distance = geometry_boundary_distance_km(previous.get("boundary"), current.get("boundary"))
            if overlap is not None:
                overlaps.append(overlap)
            if distance is not None:
                boundary_distances.append(distance)
        track["boundary_consistency"] = {
            "consecutive_overlap_min": min(overlaps) if overlaps else None,
            "consecutive_overlap_mean": sum(overlaps) / len(overlaps) if overlaps else None,
            "consecutive_boundary_distance_max_km": max(boundary_distances) if boundary_distances else None,
            "comparison_count": len(overlaps),
            "interpretation": "Observed candidate geometry comparisons; not validation",
        }
        seen_indices = [
            item.get("observation_index") for item in track["observations"]
            if isinstance(item.get("observation_index"), int)
        ]
        track["gap_count"] = sum(
            max(current - previous - 1, 0)
            for previous, current in zip(seen_indices, seen_indices[1:])
        )
        track["observation_gaps"] = [
            {
                "from_observation_index": previous,
                "to_observation_index": current,
                "missing_count": max(current - previous - 1, 0),
                "reason": "No compatible candidate was associated on intervening acquisition(s)",
            }
            for previous, current in zip(seen_indices, seen_indices[1:])
            if current - previous > 1
        ]
    return {
        "tracks": tracks,
        "excluded_candidates": excluded_candidates,
        "usable_observation_ids": usable_observation_ids,
        "degraded_observations": degraded_observations,
        "rejected_associations": rejected_associations,
        "compound_observations": compound_observations,
    }


def evaluate_temporal_identity(track_result, expected_center, min_observations=3, target_name="target lake"):
    """Describe temporal support while refusing to resolve persistent competition."""
    if isinstance(track_result, dict):
        tracks = track_result.get("tracks", [])
    else:
        tracks = track_result
    persistent = []
    for track in tracks:
        distance = haversine_km(expected_center, track.get("centroid"))
        track["distance_to_expected_center_km"] = round(distance, 3) if distance is not None else None
        if track.get("observation_count", 0) >= min_observations:
            persistent.append(track)

    near_persistent = [
        track for track in persistent
        if track.get("distance_to_expected_center_km") is not None
        and track["distance_to_expected_center_km"] <= 3.0
    ]
    if not near_persistent:
        status = "TEMPORAL_IDENTITY_NOT_ESTABLISHED"
        reasons = [f"No candidate track persisted sufficiently near the expected {target_name} location"]
    elif len(near_persistent) > 1:
        status = "TEMPORAL_IDENTITY_AMBIGUOUS"
        reasons = [f"More than one spatially persistent candidate remains near the expected {target_name} location"]
    else:
        status = "TEMPORAL_IDENTITY_SUPPORTING"
        reasons = [f"One candidate track persisted near the expected {target_name} location"]
    return {
        "identity_status": {
            "TEMPORAL_IDENTITY_SUPPORTING": IDENTITY_SUPPORTED,
            "TEMPORAL_IDENTITY_AMBIGUOUS": "IDENTITY_AMBIGUOUS",
            "TEMPORAL_IDENTITY_NOT_ESTABLISHED": IDENTITY_NOT_ESTABLISHED,
        }.get(status, IDENTITY_UNCERTAIN),
        "status": status,
        "minimum_observations": min_observations,
        "persistent_track_count": len(persistent),
        "near_persistent_track_count": len(near_persistent),
        "tracks": tracks,
        "excluded_candidates": track_result.get("excluded_candidates", []) if isinstance(track_result, dict) else [],
        "usable_observation_ids": track_result.get("usable_observation_ids", []) if isinstance(track_result, dict) else [],
        "degraded_observations": track_result.get("degraded_observations", []) if isinstance(track_result, dict) else [],
        "rejected_associations": track_result.get("rejected_associations", []) if isinstance(track_result, dict) else [],
        "compound_observations": track_result.get("compound_observations", []) if isinstance(track_result, dict) else [],
        "reasons": reasons,
        "interpretation": "Temporal persistence supports repeatability but does not prove named-lake identity",
    }


def assess_target_identity(track_result, expected_center, target_name="target lake",
                           min_observations=3, min_boundary_overlap=0.02,
                           max_boundary_distance_km=0.5):
    """Apply a conservative final identity gate to temporal candidate tracks."""
    assessment = evaluate_temporal_identity(
        track_result, expected_center, min_observations, target_name
    )
    near_tracks = [
        track for track in assessment["tracks"]
        if track.get("observation_count", 0) >= min_observations
        and track.get("distance_to_expected_center_km") is not None
        and track["distance_to_expected_center_km"] <= 3.0
    ]
    if len(near_tracks) != 1:
        return assessment

    track = near_tracks[0]
    consistency = track.get("boundary_consistency", {})
    comparison_count = consistency.get("comparison_count", 0)
    mean_overlap = consistency.get("consecutive_overlap_mean")
    max_distance = consistency.get("consecutive_boundary_distance_max_km")
    consistency_supported = (
        comparison_count >= 2
        and (
            (mean_overlap is not None and mean_overlap >= min_boundary_overlap)
            or (max_distance is not None and max_distance <= max_boundary_distance_km)
        )
    )
    if assessment["status"] == "TEMPORAL_IDENTITY_SUPPORTING" and consistency_supported:
        assessment["identity_status"] = IDENTITY_SUPPORTED
        assessment["identity_reason"] = [
            f"One {target_name} candidate track is persistent and has repeatable boundary geometry"
        ]
    else:
        assessment["identity_status"] = IDENTITY_UNCERTAIN
        reasons = [
            f"One candidate is persistent near the expected {target_name} location, but boundary evidence is insufficient"
        ]
        if comparison_count < 2:
            reasons.append("Fewer than two consecutive boundary comparisons are available")
        elif not consistency_supported:
            reasons.append("Boundary overlap and displacement do not meet the repeatability gate")
        assessment["identity_reason"] = reasons
    assessment["identity_gate"] = {
        "minimum_observations": min_observations,
        "minimum_boundary_overlap": min_boundary_overlap,
        "maximum_boundary_distance_km": max_boundary_distance_km,
        "interpretation": "Acceptance criteria, not a probability or scientific validation score",
    }
    return assessment


def _bounds_from_coordinates(geometry):
    points = list(_geometry_coordinates(geometry))
    if not points:
        return None
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return {
        "min_longitude": min(longitudes),
        "max_longitude": max(longitudes),
        "min_latitude": min(latitudes),
        "max_latitude": max(latitudes),
    }


def _geometry_part_count(geometry):
    """Count polygon parts in a GeoJSON geometry for fragmentation evidence."""
    if geometry.get("type") == "Polygon":
        return 1
    if geometry.get("type") == "MultiPolygon":
        return len(geometry.get("coordinates", []))
    return 0


def derive_gee_candidates(
    ndwi_image,
    masked_image,
    roi_geometry,
    expected_center,
    ndwi_threshold,
    valid_pixel_fraction=None,
    quality_image=None,
    scale=10,
    min_component_pixels=9,
    target_name="target lake",
    spectral_image=None,
    terrain_image=None,
):
    """Vectorize connected water candidates and return explainable identity evidence."""
    try:
        import ee

        roi = ee.Geometry(roi_geometry)
        water_mask = ndwi_image.gt(ndwi_threshold).selfMask()
        connected_pixels = water_mask.connectedPixelCount(1024, True)
        candidate_mask = water_mask.updateMask(connected_pixels.gte(min_component_pixels))
        vectors = candidate_mask.reduceToVectors(
            geometry=roi,
            scale=scale,
            geometryType="polygon",
            eightConnected=True,
            reducer=ee.Reducer.countEvery(),
            maxPixels=10_000_000,
            bestEffort=True,
        )
        quality_indicators = None
        if quality_image is not None:
            scl = quality_image.select("SCL")
            contamination = None
            indicators = []
            for scl_value, name in (
                (3, "cloud_shadow_fraction"),
                (8, "cloud_medium_fraction"),
                (9, "cloud_high_fraction"),
                (10, "cirrus_fraction"),
                (11, "snow_ice_fraction"),
            ):
                class_flag = scl.eq(scl_value)
                contamination = class_flag if contamination is None else contamination.Or(class_flag)
                indicators.append(class_flag.float().rename(name))
            indicators.append(contamination.Not().float().rename("valid_pixel_fraction"))
            quality_indicators = ee.Image.cat(indicators)

        spectral_indicators = None
        if spectral_image is not None:
            green = spectral_image.select("B3")
            swir = spectral_image.select("B11")
            red = spectral_image.select("B4")
            nir = spectral_image.select("B8")
            spectral_indicators = ee.Image.cat([
                green.subtract(swir).divide(green.add(swir)).rename("mndwi"),
                nir.subtract(red).divide(nir.add(red)).rename("ndvi"),
            ])

        def enrich_feature(feature):
            geometry = feature.geometry()
            centroid = geometry.centroid(maxError=10).coordinates()
            properties = ee.Dictionary({
                "area_sqkm": geometry.area(maxError=10).divide(1e6),
                "perimeter_m": geometry.perimeter(maxError=10),
                "centroid_longitude": centroid.get(0),
                "centroid_latitude": centroid.get(1),
                "mean_ndwi": ndwi_image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=geometry,
                    scale=scale,
                    maxPixels=10_000_000,
                    bestEffort=True,
                ).get("ndwi"),
            })
            if quality_indicators is not None:
                properties = properties.combine(quality_indicators.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=geometry.bounds(maxError=10),
                    scale=20,
                    maxPixels=10_000_000,
                    bestEffort=True,
                ), True)
            if spectral_indicators is not None:
                properties = properties.combine(spectral_indicators.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=geometry,
                    scale=20,
                    maxPixels=10_000_000,
                    bestEffort=True,
                ), True)
            if terrain_image is not None:
                terrain_indicators = ee.Image.cat([
                    terrain_image.rename("elevation_m"),
                    ee.Terrain.slope(terrain_image).rename("slope_degrees"),
                ])
                properties = properties.combine(terrain_indicators.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=geometry,
                    scale=30,
                    maxPixels=10_000_000,
                    bestEffort=True,
                ), True)
            return feature.set(properties)

        vector_info = vectors.map(enrich_feature).getInfo()
        roi_info = roi_geometry
        roi_bounds = _bounds_from_coordinates(roi_info)
        candidates = []
        for index, feature in enumerate(vector_info.get("features", []), start=1):
            feature_geometry = feature.get("geometry")
            if not feature_geometry:
                continue
            ee_feature_geometry = ee.Geometry(feature_geometry)
            feature_properties = feature.get("properties", {})
            area_sqkm = feature_properties.get("area_sqkm")
            perimeter = feature_properties.get("perimeter_m")
            centroid_info = [
                feature_properties.get("centroid_longitude"),
                feature_properties.get("centroid_latitude"),
            ]
            mean_ndwi = feature_properties.get("mean_ndwi")
            compactness = (4 * 3.141592653589793 * area_sqkm * 1_000_000) / (perimeter ** 2) if perimeter else None
            candidate_quality = {
                "quality_scope": "candidate_bounding_context",
                "valid_pixel_fraction": feature_properties.get("valid_pixel_fraction", valid_pixel_fraction),
                "cloud_shadow_fraction": feature_properties.get("cloud_shadow_fraction"),
                "cloud_medium_fraction": feature_properties.get("cloud_medium_fraction"),
                "cloud_high_fraction": feature_properties.get("cloud_high_fraction"),
                "cirrus_fraction": feature_properties.get("cirrus_fraction"),
                "snow_ice_fraction": feature_properties.get("snow_ice_fraction"),
            }
            spectral_context = {
                "mndwi": feature_properties.get("mndwi"),
                "ndvi": feature_properties.get("ndvi"),
                "source": (
                    "Sentinel-2 B3/B11/B4/B8 derived from real image"
                    if spectral_image is not None else "UNAVAILABLE"
                ),
            }
            terrain_context = {
                "elevation_m": feature_properties.get("elevation_m"),
                "slope_degrees": feature_properties.get("slope_degrees"),
                "source": (
                    "Copernicus DEM-derived terrain context"
                    if terrain_image is not None else "UNAVAILABLE"
                ),
            }
            candidate = {
                "candidate_id": f"component_{index}",
                "boundary": feature_geometry,
                "area_sqkm": round(area_sqkm, 6),
                "centroid": {"longitude": centroid_info[0], "latitude": centroid_info[1]},
                "bounds": _bounds_from_coordinates(feature_geometry),
                "mean_ndwi": mean_ndwi,
                "perimeter_m": perimeter,
                "compactness": compactness,
                "geometry_part_count": _geometry_part_count(feature_geometry),
                "spectral_context": spectral_context,
                "terrain_context": terrain_context,
                "hydrological_context": {
                    "shape_context": _shape_context({
                        "bounds": _bounds_from_coordinates(feature_geometry),
                        "compactness": compactness,
                    }),
                    "status": "DERIVED_GEOMETRIC_CONTEXT",
                },
                "quality": candidate_quality,
                "valid_pixel_fraction": candidate_quality.get("valid_pixel_fraction"),
            }
            candidates.append(candidate)

        selection = select_candidate(
            candidates, expected_center, roi_bounds, ndwi_threshold, valid_pixel_fraction, target_name
        )
        selected = selection.get("selected_candidate")
        if selected:
            selected_mask = candidate_mask.clip(ee.Geometry(selected["boundary"]))
            selection["selected_mask"] = selected_mask
        selection["method"] = {
            "water_index": "NDWI",
            "threshold": ndwi_threshold,
            "minimum_connected_pixels": min_component_pixels,
            "scale_m": scale,
            "component_selection": "evidence-ranked; largest area alone is insufficient",
        }
        return selection
    except Exception as exc:
        return {
            "identity_status": IDENTITY_NOT_ESTABLISHED,
            "selected_candidate": None,
            "candidates": [],
            "reason": [f"Candidate boundary derivation failed: {exc}"],
            "method": {
                "water_index": "NDWI",
                "threshold": ndwi_threshold,
                "minimum_connected_pixels": min_component_pixels,
                "scale_m": scale,
            },
        }
