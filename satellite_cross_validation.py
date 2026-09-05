"""Independent Sentinel-2/Landsat observation cross-validation."""

from copy import deepcopy
from datetime import datetime, timezone


SATELLITES_AGREE = "SATELLITES_AGREE"
SATELLITES_DISAGREE = "SATELLITES_DISAGREE"
NO_INDEPENDENT_DATA = "NO_INDEPENDENT_DATA"


def query_landsat_availability(region_geometry, start_date, end_date, cloud_cover_max=60):
    """Query real Landsat 8/9 availability without inventing corroboration."""
    try:
        import ee

        collection = (
            ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
            .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
            .filterBounds(ee.Geometry(region_geometry))
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt("CLOUD_COVER", cloud_cover_max))
            .sort("system:time_start")
        )
        count = collection.size().getInfo()
        result = {
            "status": "AVAILABLE" if count else "NO_INDEPENDENT_DATA",
            "collection": "LANDSAT/LC08/C02/T1_L2 + LANDSAT/LC09/C02/T1_L2",
            "requested_date_range": {"start": start_date, "end": end_date},
            "cloud_cover_limit": cloud_cover_max,
            "available_acquisitions": count,
            "observations": [],
            "provenance": {
                "type": "REAL_SATELLITE_DATA",
                "method": "GEE Landsat 8/9 collection availability query",
                "limitations": [
                    "Availability is not corroboration or identity validation",
                    "No Landsat water-area agreement is asserted by this query",
                ],
            },
        }
        if count:
            images = collection.toList(min(count, 3))
            for index in range(min(count, 3)):
                properties = ee.Image(images.get(index)).getInfo().get("properties", {})
                result["observations"].append({
                    "image_id": properties.get("LANDSAT_PRODUCT_ID") or properties.get("system:index"),
                    "acquisition_time": properties.get("DATE_ACQUIRED") or properties.get("system:time_start"),
                    "cloud_cover_percent": properties.get("CLOUD_COVER"),
                })
        return result
    except Exception as exc:
        return {
            "status": NO_INDEPENDENT_DATA,
            "collection": "LANDSAT/LC08/C02/T1_L2 + LANDSAT/LC09/C02/T1_L2",
            "requested_date_range": {"start": start_date, "end": end_date},
            "available_acquisitions": 0,
            "observations": [],
            "reason": f"Landsat availability query failed: {exc}",
            "provenance": {
                "type": "UNAVAILABLE",
                "method": "GEE Landsat 8/9 collection availability query",
                "limitations": ["No independent satellite corroboration was produced"],
            },
        }

_INVALID_STATUSES = {
    "ERROR",
    "UNAVAILABLE",
    "STALE_IMAGERY",
    "NO_SUITABLE_IMAGERY",
    "MASKING_FAILED",
    "PROCESSING_FAILED",
    "NO_VALID_PIXELS",
}


def _satellite_record(observation):
    if not isinstance(observation, dict):
        return {}, {}
    satellite = observation.get("satellite")
    return (satellite if isinstance(satellite, dict) else observation), observation


def _timestamp(record):
    value = record.get("acquisition_time") or record.get("date")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _area_value(record):
    water_area = record.get("water_area")
    if isinstance(water_area, dict):
        value = water_area.get("area_sqkm")
        if isinstance(value, (int, float)):
            return float(value)
    value = record.get("water_area_sqkm")
    return float(value) if isinstance(value, (int, float)) else None


def _baseline_comparison(record):
    comparison = record.get("seasonal_comparison") or record.get("baseline_comparison") or {}
    baseline = comparison.get("baseline") or {}
    statistics = baseline.get("statistics") or {}
    baseline_value = comparison.get("baseline_value", statistics.get("mean"))
    current_value = comparison.get("current_value", _area_value(record))
    deviation_percentage = comparison.get("deviation_percentage")
    if deviation_percentage is None and isinstance(baseline_value, (int, float)) and baseline_value != 0 and isinstance(current_value, (int, float)):
        deviation_percentage = ((current_value - baseline_value) / baseline_value) * 100
    if not isinstance(deviation_percentage, (int, float)):
        contextual = record.get("satellite_change_evidence") or record.get("change_evidence") or {}
        magnitude = contextual.get("change_magnitude") or {}
        deviation_percentage = magnitude.get("water_area_deviation_percentage")
    return {
        "current_area_sqkm": current_value,
        "baseline_area_sqkm": baseline_value,
        "deviation_percentage": deviation_percentage,
    }


def _validity(record, root):
    status = record.get("status") or root.get("status")
    validity_status = record.get("validity_status") or root.get("validity_status")
    if status in _INVALID_STATUSES or validity_status == "UNAVAILABLE":
        return False, f"Observation is not usable: status={status!r}, validity={validity_status!r}"
    if record.get("quality_masking", {}).get("status") not in {None, "APPLIED"}:
        return False, "Satellite quality masking was not applied"
    cloud_cover = record.get("cloud_cover_percent")
    if isinstance(cloud_cover, (int, float)) and cloud_cover >= 50:
        return False, "Satellite cloud cover is too high for independent comparison"
    data_quality = record.get("data_quality") or {}
    valid_fraction = data_quality.get("valid_pixel_fraction")
    if isinstance(valid_fraction, (int, float)) and valid_fraction < 0.6:
        return False, "Satellite valid-pixel fraction is too low for independent comparison"
    if _timestamp(record) is None:
        return False, "Acquisition time is missing or invalid"
    if _area_value(record) is None:
        return False, "Water-area measurement is missing or invalid"
    identity = (
        root.get("identity_status")
        or (root.get("temporal_evidence") or {}).get("identity_status")
        or (record.get("candidate_detection") or {}).get("identity_status")
    )
    if identity in {"IDENTITY_AMBIGUOUS", "IDENTITY_UNCERTAIN", "IDENTITY_NOT_ESTABLISHED"}:
        return False, f"Lake identity is not sufficiently supported: {identity}"
    return True, None


def _target_key(record, root):
    return (
        root.get("region")
        or record.get("region")
        or record.get("lake_id")
        or record.get("target_id")
    )


def cross_validate_observation(
    primary_obs: dict,
    secondary_obs: dict,
    *,
    temporal_window_days=5,
    area_tolerance_percentage=20.0,
):
    """Compare supplied Sentinel-2 and Landsat 8/9 observations.

    This function performs no secondary-data retrieval and calculates no risk
    score. Agreement is observational corroboration only, not evidence of a
    GLOF event or probability.
    """
    primary, primary_root = _satellite_record(primary_obs)
    secondary, secondary_root = _satellite_record(secondary_obs)
    result = {
        "status": NO_INDEPENDENT_DATA,
        "meaning": "No valid independent Landsat observation was available within the matching window.",
        "temporal_window_days": temporal_window_days,
        "area_tolerance_percentage": area_tolerance_percentage,
        "primary": {
            "satellite": primary.get("satellite", "Sentinel-2"),
            "image_id": primary.get("image_id"),
            "acquisition_time": primary.get("acquisition_time"),
        },
        "secondary": {
            "satellite": secondary.get("satellite"),
            "image_id": secondary.get("image_id"),
            "acquisition_time": secondary.get("acquisition_time"),
        },
        "matching": {"matched": False, "difference_days": None},
        "evidence": {},
        "uncertainty": {
            "level": "UNCHANGED_PRIMARY_ONLY",
            "confidence": "PRIMARY_ONLY",
            "reasons": [],
        },
        "provenance": {
            "type": "DERIVED_FROM_REAL_DATA",
            "method": "Independent supplied satellite observation comparison",
            "limitations": [
                "Agreement is observational corroboration, not proof of a GLOF",
                "No Landsat retrieval is performed by this validation engine",
            ],
        },
        "decision_support": {
            "risk_score_changed": False,
            "warning_triggered": False,
        },
    }

    primary_valid, primary_reason = _validity(primary, primary_root)
    secondary_valid, secondary_reason = _validity(secondary, secondary_root)
    primary_satellite = str(primary.get("satellite", "Sentinel-2")).upper()
    secondary_satellite = str(secondary.get("satellite", "")).upper()
    if "SENTINEL-2" not in primary_satellite and "SENTINEL2" not in primary_satellite:
        primary_valid = False
        primary_reason = "Primary observation is not identified as Sentinel-2"
    if not any(platform in secondary_satellite for platform in ("LANDSAT-8", "LANDSAT 8", "LANDSAT-9", "LANDSAT 9")):
        secondary_valid = False
        secondary_reason = "Secondary observation is not identified as Landsat 8/9 OLI"
    primary_time = _timestamp(primary)
    secondary_time = _timestamp(secondary)
    if primary_time and secondary_time:
        difference_days = abs((primary_time - secondary_time).total_seconds()) / 86400
        result["matching"]["difference_days"] = difference_days
        result["matching"]["matched"] = difference_days <= temporal_window_days
    if not secondary_valid:
        result["uncertainty"]["reasons"].append(
            secondary_reason or "No valid Landsat observation was supplied"
        )
        return result
    if not primary_valid:
        result["uncertainty"]["reasons"].append(primary_reason)
        result["uncertainty"]["level"] = "HIGH"
        result["uncertainty"]["confidence"] = "PRIMARY_INVALID"
        result["meaning"] = "The primary Sentinel-2 observation was not valid enough for independent comparison."
        return result
    if not result["matching"]["matched"]:
        result["uncertainty"]["reasons"].append(
            "The valid Landsat acquisition is outside the configured temporal matching window"
        )
        return result
    if _target_key(primary, primary_root) and _target_key(secondary, secondary_root) and _target_key(primary, primary_root) != _target_key(secondary, secondary_root):
        result["uncertainty"]["reasons"].append("Observations identify different targets")
        result["uncertainty"]["level"] = "HIGH"
        result["uncertainty"]["confidence"] = "TARGET_MISMATCH"
        result["meaning"] = "The supplied observations do not refer to the same configured target."
        return result

    primary_change = _baseline_comparison(primary)
    secondary_change = _baseline_comparison(secondary)
    primary_deviation = primary_change["deviation_percentage"]
    secondary_deviation = secondary_change["deviation_percentage"]
    if not isinstance(primary_deviation, (int, float)) or not isinstance(secondary_deviation, (int, float)):
        result["uncertainty"]["reasons"].append("Seasonal change evidence is missing from one or both observations")
        result["uncertainty"]["level"] = "HIGH"
        result["uncertainty"]["confidence"] = "CHANGE_EVIDENCE_INSUFFICIENT"
        result["meaning"] = "The observations matched in time, but neither source supplied comparable seasonal change evidence."
        return result

    difference = abs(primary_deviation - secondary_deviation)
    primary_anomaly = abs(primary_deviation) > area_tolerance_percentage
    secondary_anomaly = abs(secondary_deviation) > area_tolerance_percentage
    result["evidence"] = {
        "primary": primary_change,
        "secondary": secondary_change,
        "deviation_difference_percentage_points": difference,
        "same_anomaly_direction": (primary_deviation >= 0) == (secondary_deviation >= 0),
        "primary_anomaly": primary_anomaly,
        "secondary_anomaly": secondary_anomaly,
    }
    result["provenance"]["sources"] = [
        deepcopy(primary.get("provenance") or primary_root.get("provenance")),
        deepcopy(secondary.get("provenance") or secondary_root.get("provenance")),
    ]
    if primary_anomaly != secondary_anomaly or not result["evidence"]["same_anomaly_direction"]:
        result["status"] = SATELLITES_DISAGREE
        result["meaning"] = "Sentinel-2 and Landsat provide conflicting evidence about the lake-area anomaly."
        result["uncertainty"] = {
            "level": "HIGH",
            "confidence": "CONFLICTING_INDEPENDENT_EVIDENCE",
            "reasons": ["One source indicates an anomaly while the other does not, or their directions conflict"],
        }
    else:
        result["status"] = SATELLITES_AGREE
        result["meaning"] = "Sentinel-2 and Landsat provide consistent independent evidence about the lake-area change."
        result["uncertainty"] = {
            "level": "LOWER_WITH_CORROBORATION",
            "confidence": "INDEPENDENT_CORROBORATION",
            "reasons": ["Both sources match in time and support the same seasonal anomaly direction"],
        }
    return result