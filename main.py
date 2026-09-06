"""
main.py - Quick start and demo script for G-ALERT backend
"""

from satellite.region_config import (
    HIMALAYAN_REGIONS,
    get_authoritative_reference,
    get_lake_geometry,
    get_region_bounds,
    get_region_info,
)
from satellite.gee_pipeline import initialize_gee_pipeline
from satellite.image_cache import get_image_cache
from simulation.sensor_simulator import SensorNetwork, SensorObservation
from simulation.nepal_disaster import NepalDisasterScenario
from risk_engine import RiskEngine, RiskAssessment
from ai.yolov8_detector import Detection, AIObservation, YOLOv8Detector
from satellite.ndwi_analysis import NDWIAnalyzer, WaterObservation
from satellite.lake_detection import (
    IDENTITY_SUPPORTED,
    build_temporal_tracks,
    derive_gee_candidates,
    assess_target_identity,
    can_publish_observed_area,
    candidate_temporal_eligibility,
    assess_lake_likeness,
    evaluate_temporal_identity,
    geometry_center,
)
from provenance import (
    DERIVED_FROM_REAL_DATA,
    PROTOTYPE_ASSUMPTION,
    REAL_SATELLITE_DATA,
    SCIENTIFIC_SIMULATION,
    SIMULATED_SENSOR_DATA,
    UNAVAILABLE,
    provenance,
)
from observation_store import ObservationStore
from seasonal_baseline import evaluate_against_seasonal_baseline
from contextual_change import evaluate_contextual_change
from gee_reliability import GEEReliabilityLayer, merge_reliability_metadata
from execution_manager import MonitoringExecutionManager
from early_warning_status import (
    build_human_warning,
    evaluate_early_warning_status,
    INSUFFICIENT_DATA,
)
from alert_event_lifecycle import evaluate_warning_confirmation
from satellite.multi_signal_identity import (
    build_evidence_lifecycle,
    evaluate_multi_signal_identity,
)
from authoritative_boundary import IDENTITY_AMBIGUOUS
from authoritative_boundary import validate_authoritative_boundary
from satellite.identity_association import associate_temporal_identity
from satellite_cross_validation import query_landsat_availability
from weather_integration import fetch_weather_observation
from downstream_impact import build_downstream_impact
from downstream_provider import fetch_automated_downstream_context
from impact_mapping import build_impact_mapping
from region_integrity import validate_observation

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone


INTEGRATED_RESULT_KEYS = (
    "status",
    "region",
    "satellite",
    "satellite_change",
    "satellite_change_evidence",
    "sensors",
    "ai",
    "risk",
    "alert_confirmation",
    "downstream_impact",
    "impact_mapping",
    "downstream_exposure",
    "history",
)


def _date_range(start_date, end_date):
    """Resolve an explicit range or a recent range for a latest-image request."""
    if start_date and not end_date:
        end_date = (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    if not start_date and end_date:
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    if not start_date and not end_date:
        end = datetime.utcnow().date()
        start_date = (end - timedelta(days=30)).isoformat()
        end_date = (end + timedelta(days=1)).isoformat()
    return start_date, end_date


def _temporal_date_range(start_date, end_date):
    """Resolve temporal requests to a six-month historical window by default."""
    if not start_date and not end_date:
        end = datetime.utcnow().date() + timedelta(days=1)
        return (end - timedelta(days=180)).isoformat(), end.isoformat()
    return _date_range(start_date, end_date)


def _temporal_acquisition_indices(total, max_observations):
    """Select distinct, evenly distributed acquisitions from a sorted collection."""
    count = min(total, max_observations)
    return sorted({
        round(index * (total - 1) / max(count - 1, 1))
        for index in range(count)
    })


def _temporal_discovery_geometry(search_geometry, configured_geometry, geometry_metadata):
    """Use a trusted polygon when present, otherwise retain the broad search ROI."""
    trusted = geometry_metadata.get("status") in {
        "VALIDATED", "AUTHORITATIVE", "TRUSTED"
    }
    return configured_geometry if trusted else search_geometry


def _acquisition_is_in_requested_range(acquisition_ms, start_date, end_date):
    """Check whether a GEE acquisition is inside the requested half-open range."""
    if not acquisition_ms:
        return False
    acquisition_date = datetime.fromtimestamp(acquisition_ms / 1000, timezone.utc).date()
    return (
        datetime.strptime(start_date, "%Y-%m-%d").date()
        <= acquisition_date
        < datetime.strptime(end_date, "%Y-%m-%d").date()
    )


def glof_ai_signal_for_risk(ai_status):
    """
    AI contribution to GLOF risk for the integrated monitoring path.

    Generic YOLOv8 COCO detections are not a GLOF-domain signal.
    Only a future domain-specific detector would return a non-zero value.
    """
    if ai_status == "NO_DOMAIN_SIGNAL":
        return 0.0
    return 0.0


def _integrated_result_skeleton(region_key, status, mode="monitoring", reason=None, processed_at=None):
    """Build the frontend-facing integrated result shape (success and error)."""
    processed_at = processed_at or (datetime.utcnow().isoformat() + "Z")
    region = get_region_info(region_key)
    result = {
        "status": status,
        "region": region_key,
        "region_name": region["name"] if region else None,
        "mode": mode,
        "source": "Google Earth Engine",
        "collection": "COPERNICUS/S2_SR_HARMONIZED",
        "provenance": provenance(
            UNAVAILABLE,
            source="No observation produced",
            limitations=["This response does not contain a usable satellite observation"],
        ),
        "geometry": {
            "status": region.get("geometry_status") if region else "UNKNOWN",
            "source": region.get("geometry_source") if region else None,
            "measurement_scope": "UNKNOWN",
        },
        "downstream_impact": build_downstream_impact(region_key, region),
        "impact_mapping": {
            "region": region_key,
            "status": "UNAVAILABLE",
            "classification": "SCREENING_APPROXIMATE",
            "corridor": None,
            "exposed_settlements": [],
            "exposed_infrastructure": [],
            "population": {"value": None, "status": "UNAVAILABLE"},
            "confidence": "LOW",
            "limitations": [
                "No impact corridor was produced; missing data does not imply no impact",
                "This feature is approximate screening, not hydrodynamic flood simulation",
            ],
        },
        "processed_at": processed_at,
        "satellite": {"status": "NOT_AVAILABLE"},
        "weather": {
            "region": region_key,
            "status": "UNAVAILABLE",
            "source": "Open-Meteo",
            "rainfall_mmph": None,
            "rainfall_24h_mm": None,
            "observation_time": None,
            "provenance": {
                "type": "UNAVAILABLE",
                "source": "Open-Meteo",
                "limitations": ["No weather observation was produced"],
            },
        },
        "satellite_change": {"region": region_key, "status": "NOT_AVAILABLE"},
        "satellite_change_evidence": {"region": region_key, "status": "NOT_AVAILABLE"},
        "risk_change_explanation": {"region": region_key, "status": "NOT_AVAILABLE"},
        "human_warning": {
            "region": region_key,
            "status": INSUFFICIENT_DATA,
            "level": "INSUFFICIENT DATA",
            "message": "A warning decision cannot be made from the available evidence.",
            "reasons": ["No usable observation evidence is available."],
            "supporting_evidence": [],
            "recommended_action": "Obtain usable observations before making a warning decision; do not interpret missing data as safety.",
            "technical_details_separate": True,
        },
        "alert_confirmation": {
            "region": region_key,
            "state": "NO_ACTIVE_WARNING",
            "warning_status": INSUFFICIENT_DATA,
            "confirmed": False,
            "persistent": False,
            "reason": "No usable observation evidence is available.",
        },
        "data_confidence": {
            "region": region_key,
            "level": "LOW",
            "is_probability": False,
            "summary": "Data confidence is LOW because no usable observation was produced.",
            "reasons": ["usable observation evidence is unavailable"],
            "factors": {},
            "limitations": ["This response does not contain a usable satellite observation"],
        },
        "sensors": {
            "status": "NOT_RUN",
            "note": "Virtual sensors run only in simulation mode",
            "simulated": True,
        },
        "ai": {
            "status": "NOT_AVAILABLE",
            "signal": 0.0,
            "note": "Generic YOLOv8n is not a GLOF-domain signal",
        },
        "risk": None,
        "decision_support": {
            "status": "UNAVAILABLE",
            "reason": "No usable observation has been assessed",
            "risk_available": False,
        },
        "downstream_exposure": (region or {}).get("downstream_exposure"),
        "history": [],
    }
    if reason is not None:
        result["reason"] = reason
    return result


_REGION_SCOPED_SECTIONS = (
    "weather",
    "human_warning",
    "data_confidence",
    "alert_confirmation",
    "satellite_change",
    "risk_change_explanation",
    "satellite_change_evidence",
)


def _validate_nested_region_identity(observation, region_key):
    """Validate explicit region metadata on region-scoped response sections."""
    for section_name in _REGION_SCOPED_SECTIONS:
        section = observation.get(section_name)
        if isinstance(section, dict) and section.get("region") is not None:
            if section["region"] != region_key:
                raise ValueError(
                    f"{section_name}.region does not match requested region {region_key!r}"
                )


def _attach_risk_and_history(result, engine, satellite_signal, ai_signal, sensor_signal, region_key):
    """Record one RiskEngine assessment and expose instance history on the result."""
    risk = engine.assess_risk(
        satellite_signal=satellite_signal,
        ai_signal=ai_signal,
        sensor_signal=sensor_signal,
        region=region_key,
    )
    risk.update({"region": region_key, "source": "prototype_demo_logic"})
    result["risk"] = risk
    result["history"] = list(engine.history)
    return result


def _previous_observation_change(store, region_key, current_area_sqkm):
    """Compare the current valid area with the newest prior valid observation."""
    previous_observation = store.get_previous_valid_observation(region_key)
    change = {
        "current_area_sqkm": current_area_sqkm,
        "previous_area_sqkm": None,
        "previous_observation_id": None,
        "previous_acquisition_time": None,
        "previous_observation_percent_change": None,
        "trend": None,
    }
    if not previous_observation or not isinstance(current_area_sqkm, (int, float)):
        return change

    previous_payload = previous_observation.get("observation") or {}
    previous_satellite = previous_payload.get("satellite") or {}
    previous_area_sqkm = (previous_satellite.get("water_area") or {}).get("area_sqkm")
    if not isinstance(previous_area_sqkm, (int, float)):
        return change

    previous_change = NDWIAnalyzer().analyze_water_change(
        current_area_sqkm,
        previous_area_sqkm,
    )
    change.update({
        "current_area_sqkm": current_area_sqkm,
        "previous_area_sqkm": previous_area_sqkm,
        "previous_observation_id": previous_observation.get("observation_id"),
        "previous_acquisition_time": previous_satellite.get("acquisition_time"),
        "previous_observation_percent_change": previous_change.get("percent_change"),
        "trend": previous_change.get("trend", "").upper(),
    })
    return change


def _risk_change_explanation(store, region_key, current_observation):
    """Explain risk movement using the newest prior valid risk observation."""
    current_risk = current_observation.get("risk") or {}
    current_score = current_risk.get("risk_score")
    change = {
        "region": region_key,
        "status": "NOT_AVAILABLE",
        "trend": None,
        "previous_risk_score": None,
        "current_risk_score": current_score,
        "previous_risk_level": None,
        "current_risk_level": current_risk.get("risk_level"),
        "previous_risk_status": None,
        "current_risk_status": current_risk.get("assessment_status"),
        "score_change": None,
        "explanation": "No previous valid risk result is available for comparison.",
        "contributing_changes": {},
    }
    previous_record = store.get_previous_valid_risk_observation(region_key)
    if not previous_record or not isinstance(current_score, (int, float)):
        return change

    previous_observation = previous_record.get("observation") or {}
    previous_risk = previous_observation.get("risk") or {}
    previous_score = previous_risk.get("risk_score")
    score_change = round(current_score - previous_score, 4)
    trend = (
        "INCREASING" if score_change > 0
        else "DECREASING" if score_change < 0
        else "STABLE"
    )

    current_satellite_change = current_observation.get("satellite_change") or {}
    previous_satellite_change = previous_observation.get("satellite_change") or {}
    current_signals = current_risk.get("signals") or {}
    previous_signals = previous_risk.get("signals") or {}
    current_missing = current_risk.get("missing_inputs") or []
    previous_missing = previous_risk.get("missing_inputs") or []
    current_unavailable = current_risk.get("unavailable_information") or []
    previous_unavailable = previous_risk.get("unavailable_information") or []

    satellite_change = None
    if (
        isinstance(current_signals.get("satellite"), (int, float))
        and isinstance(previous_signals.get("satellite"), (int, float))
    ):
        satellite_change = round(
            current_signals["satellite"] - previous_signals["satellite"], 4
        )
    contributing_changes = {
        "lake_area": {
            "previous_area_sqkm": previous_satellite_change.get("current_area_sqkm"),
            "current_area_sqkm": current_satellite_change.get("current_area_sqkm"),
            "percent_change": current_satellite_change.get(
                "previous_observation_percent_change"
            ),
            "trend": current_satellite_change.get("trend"),
        },
        "satellite_signal": {
            "previous": previous_signals.get("satellite"),
            "current": current_signals.get("satellite"),
            "change": satellite_change,
            "evidence_status": current_satellite_change.get("status"),
        },
        "confidence": {
            "previous": previous_risk.get("confidence"),
            "current": current_risk.get("confidence"),
            "data_quality_confidence": current_satellite_change.get(
                "data_quality_confidence"
            ),
        },
        "evidence_availability": {
            "previous_missing_inputs": previous_missing,
            "current_missing_inputs": current_missing,
            "previous_unavailable_information": previous_unavailable,
            "current_unavailable_information": current_unavailable,
        },
    }
    reasons = [
        f"Risk score changed from {previous_score:.4f} to {current_score:.4f} ({trend.lower()})."
    ]
    area_change = contributing_changes["lake_area"]
    if area_change["percent_change"] is not None:
        reasons.append(
            f"Lake area changed {area_change['percent_change']:.1f}% ({area_change['trend']})."
        )
    if satellite_change is not None and satellite_change != 0:
        reasons.append(f"Satellite risk signal changed by {satellite_change:+.4f}.")
    if current_risk.get("confidence") != previous_risk.get("confidence"):
        reasons.append(
            f"Risk confidence changed from {previous_risk.get('confidence')} to {current_risk.get('confidence')}."
        )
    if current_missing != previous_missing or current_unavailable != previous_unavailable:
        reasons.append("The available or withheld evidence changed between observations.")

    change.update({
        "status": "CALCULATED",
        "trend": trend,
        "previous_risk_score": previous_score,
        "previous_risk_level": previous_risk.get("risk_level"),
        "previous_risk_status": previous_risk.get("assessment_status"),
        "score_change": score_change,
        "explanation": " ".join(reasons),
        "contributing_changes": contributing_changes,
        "previous_observation_id": previous_record.get("observation_id"),
        "previous_acquisition_time": (
            (previous_observation.get("satellite") or {}).get("acquisition_time")
        ),
    })
    return change


def _data_confidence_summary(observation):
    """Summarize evidence quality without treating confidence as probability."""
    observation = observation if isinstance(observation, dict) else {}
    satellite = observation.get("satellite") or {}
    risk = observation.get("risk") or {}
    quality = satellite.get("data_quality") or {}
    masking = satellite.get("quality_masking") or {}
    identity = (
        (observation.get("temporal_evidence") or {}).get("identity_status")
        or (satellite.get("candidate_detection") or {}).get("identity_status")
        or observation.get("identity_status")
        or "UNAVAILABLE"
    )
    seasonal = satellite.get("seasonal_comparison") or {}
    provenance_record = observation.get("provenance") or {}
    limitations = list(provenance_record.get("limitations") or [])
    contextual_change = observation.get("satellite_change_evidence") or {}
    limitations.extend(contextual_change.get("limitations") or [])
    limitations.extend(contextual_change.get("uncertainty", {}).get("reasons") or [])
    limitations.extend(risk.get("unavailable_information") or [])
    limitations.extend(risk.get("assumptions") or [])
    limitations.extend((observation.get("weather") or {}).get("provenance", {}).get("limitations") or [])
    limitations.extend((observation.get("downstream_impact") or {}).get("limitations") or [])
    limitations.extend((observation.get("impact_mapping") or {}).get("limitations") or [])
    limitations = list(dict.fromkeys(str(item) for item in limitations if item))

    valid_pixel_fraction = quality.get("valid_pixel_fraction")
    imagery_quality = "AVAILABLE"
    imagery_reasons = []
    if satellite.get("status") in {
        None, "NOT_AVAILABLE", "NO_SUITABLE_IMAGERY", "STALE_IMAGERY",
        "MASKING_FAILED", "PROCESSING_FAILED", "NO_VALID_PIXELS",
    }:
        imagery_quality = "INSUFFICIENT"
        imagery_reasons.append("usable satellite imagery or processing output is unavailable")
    elif masking.get("status") != "APPLIED":
        imagery_quality = "DEGRADED"
        imagery_reasons.append("satellite quality masking was not applied")
    elif isinstance(valid_pixel_fraction, (int, float)) and valid_pixel_fraction < 0.6:
        imagery_quality = "DEGRADED"
        imagery_reasons.append("valid-pixel fraction is below the existing quality threshold")
    elif isinstance(quality.get("confidence"), (int, float)) and quality["confidence"] < 0.6:
        imagery_quality = "DEGRADED"
        imagery_reasons.append("imagery quality confidence is below 0.6")

    identity_quality = "HIGH" if identity == "IDENTITY_SUPPORTED" else (
        "INSUFFICIENT" if identity in {"UNAVAILABLE", "IDENTITY_AMBIGUOUS", "IDENTITY_UNCERTAIN", "IDENTITY_NOT_ESTABLISHED"}
        else "DEGRADED"
    )
    identity_reasons = [] if identity_quality == "HIGH" else [
        f"lake identity is {identity}"
    ]
    baseline_quality = "HIGH" if seasonal.get("status") == "VALID" else "INSUFFICIENT"
    baseline_reasons = [] if baseline_quality == "HIGH" else [
        "historical or seasonal baseline is unavailable or insufficient"
    ]
    missing_inputs = list(risk.get("missing_inputs") or [])
    unavailable = list(risk.get("unavailable_information") or [])
    evidence_quality = "HIGH" if not missing_inputs and not unavailable else "DEGRADED"
    evidence_reasons = []
    if missing_inputs:
        evidence_reasons.append("missing signals: " + ", ".join(missing_inputs))
    if unavailable:
        evidence_reasons.append("unavailable information is present")

    weather_present = "weather" in observation
    weather = observation.get("weather") or {}
    weather_quality = (
        "HIGH" if weather.get("status") == "SUCCESS"
        else "INSUFFICIENT" if weather_present
        else "NOT_ASSESSED"
    )
    weather_reasons = (
        [] if weather_quality in {"HIGH", "NOT_ASSESSED"}
        else [f"weather data is {weather.get('status', 'UNAVAILABLE').lower()}" ]
    )

    simulated = (
        observation.get("mode") == NEPAL_SIMULATION_MODE
        or observation.get("simulated") is True
        or provenance_record.get("type") in {SIMULATED_SENSOR_DATA, SCIENTIFIC_SIMULATION}
    )
    if simulated:
        limitations.append("This output contains simulated rather than field-observed inputs")

    hard_degradation = (
        observation.get("status") in {"ERROR", "NO_SUITABLE_IMAGERY", "STALE_IMAGERY", "SATELLITE_PROCESSING_ERROR"}
        or imagery_quality == "INSUFFICIENT"
        or identity_quality == "INSUFFICIENT"
    )
    moderate_degradation = (
        simulated
        or imagery_quality == "DEGRADED"
        or identity_quality == "DEGRADED"
        or baseline_quality == "INSUFFICIENT"
        or evidence_quality == "DEGRADED"
        or weather_quality == "INSUFFICIENT"
        or bool(limitations)
    )
    level = "LOW" if hard_degradation else "MEDIUM" if moderate_degradation else "HIGH"
    reasons = imagery_reasons + identity_reasons + baseline_reasons + evidence_reasons + weather_reasons
    if simulated:
        reasons.append("one or more inputs are explicitly simulated")
    if not reasons and limitations:
        reasons.append("known methodological limitations remain even though required evidence is present")

    return {
        "region": observation.get("region"),
        "level": level,
        "is_probability": False,
        "summary": (
            f"Data confidence is {level}; this describes evidence quality and completeness, "
            "not the probability of a GLOF."
        ),
        "reasons": list(dict.fromkeys(reasons)),
        "factors": {
            "imagery_quality": {
                "status": imagery_quality,
                "quality_masking": masking.get("status"),
                "valid_pixel_fraction": valid_pixel_fraction,
                "confidence": quality.get("confidence"),
            },
            "lake_identity": {
                "status": identity,
                "quality": identity_quality,
            },
            "historical_baseline": {
                "status": seasonal.get("status", "NOT_AVAILABLE"),
                "quality": baseline_quality,
                "observation_count": (seasonal.get("baseline") or {}).get("observation_count"),
            },
            "evidence_availability": {
                "status": evidence_quality,
                "missing_inputs": missing_inputs,
                "unavailable_information": unavailable,
            },
            "weather": {
                "status": weather.get("status", "UNAVAILABLE"),
                "quality": weather_quality,
                "observation_time": weather.get("observation_time"),
                "source": weather.get("source"),
                "rainfall_mmph": weather.get("rainfall_mmph"),
                "rainfall_24h_mm": weather.get("rainfall_24h_mm"),
            },
            "provenance": {
                "type": provenance_record.get("type", "UNAVAILABLE"),
                "source": provenance_record.get("source"),
            },
        },
        "limitations": limitations,
    }


def _public_candidate_detection(candidate_detection):
    """Remove EE server objects before returning candidate evidence as JSON."""
    if not candidate_detection:
        return None
    return {
        key: value for key, value in candidate_detection.items() if key != "selected_mask"
    }


def _run_integrated_monitoring(region_key, start_date=None, end_date=None, mode="monitoring"):
    """Return a fresh, API-ready observation for one configured region."""
    processed_at = datetime.utcnow().isoformat() + "Z"
    region = get_region_info(region_key)
    if region is None:
        return _integrated_result_skeleton(
            region_key,
            status="ERROR",
            mode=mode,
            reason="Unknown monitoring region",
            processed_at=processed_at,
        )

    start_date, end_date = _temporal_date_range(start_date, end_date)
    bounds = get_region_bounds(region_key)
    lake_geometry, geometry_metadata = get_lake_geometry(region_key)
    result = _integrated_result_skeleton(
        region_key,
        status="ERROR",
        mode=mode,
        processed_at=processed_at,
    )
    result["requested_date_range"] = {"start": start_date, "end": end_date}
    if mode == "monitoring":
        result["weather"] = fetch_weather_observation(
            region["latitude"], region["longitude"]
        )
        result["weather"]["region"] = region_key
        automated_downstream = fetch_automated_downstream_context(
            region_key,
            region["latitude"],
            region["longitude"],
            geometry=bounds,
        )
        result["downstream_impact"] = build_downstream_impact(
            region_key, region, automated_downstream
        )
        result["impact_mapping"] = build_impact_mapping(
            region_key, region, automated_downstream
        )

    reliability = GEEReliabilityLayer()
    initialization = reliability.execute(
        initialize_gee_pipeline,
        stage="GEE_AUTHENTICATION",
        validator=lambda value: value is not None,
    )
    if not initialization["ok"]:
        result["reason"] = initialization["reason"]
        return merge_reliability_metadata(result, initialization)
    pipeline = initialization["value"]

    # Use fallback-enabled image retrieval for robust live demos.
    # coverage_geometry=lake_geometry verifies the selected image actually
    # covers the lake analysis box (filterBounds only guarantees intersection
    # with the large search region, which previously produced empty pixels,
    # NDWI=null and water area 0 for tiles like T45RUL at Tsho Rolpa).
    acquisition = reliability.execute(
        lambda: pipeline.get_sentinel2_image_with_fallback(
            bounds, start_date, end_date, cloud_cover_max=20,
            coverage_geometry=lake_geometry
        ),
        stage="IMAGERY_ACQUISITION",
        validator=lambda value: (
            isinstance(value, tuple)
            and len(value) == 2
            and value[0] is not None
        ),
    )
    if not acquisition["ok"]:
        result["image_search_metadata"] = (
            acquisition.get("value", (None, {}))[1]
            if isinstance(acquisition.get("value"), tuple)
            else {}
        )
        result["status"] = (
            "NO_SUITABLE_IMAGERY"
            if acquisition.get("error_category") == "EMPTY_OR_UNUSABLE_RESULT"
            else "ERROR"
        )
        result["reason"] = acquisition["reason"]
        return merge_reliability_metadata(result, acquisition)

    image, search_metadata = acquisition["value"]
    if image is None:
        result["status"] = "NO_SUITABLE_IMAGERY"
        result["reason"] = (
            "No suitable Sentinel-2 imagery available even with expanded search: "
            "no image covers the lake analysis area (explicit no-data, not water_area=0)"
        )
        result["satellite"] = {
            "status": "NO_SUITABLE_IMAGERY",
            "region": region_key,
            "water_area": None,
        }
        result["image_search_metadata"] = search_metadata
        result["decision_support"] = {
            "status": "UNAVAILABLE",
            "reason": result["reason"],
            "risk_available": False,
        }
        return result
    
    # Add search metadata to result for transparency
    result["image_search_metadata"] = search_metadata

    import ee

    geometry = ee.Geometry(bounds)
    metadata = pipeline.last_metadata.get("properties", {})
    acquisition_ms = metadata.get("system:time_start")
    acquisition_time = datetime.fromtimestamp(acquisition_ms / 1000, timezone.utc).isoformat() if acquisition_ms else None
    if not _acquisition_is_in_requested_range(acquisition_ms, start_date, end_date):
        result["status"] = "STALE_IMAGERY"
        result["reason"] = "Selected imagery is outside the requested observation period"
        result["satellite"] = {
            "status": "STALE_IMAGERY",
            "region": region_key,
            "image_id": metadata.get("system:index"),
            "acquisition_time": acquisition_time,
            "requested_date_range": {"start": start_date, "end": end_date},
            "water_area": None,
            "provenance": provenance(
                REAL_SATELLITE_DATA,
                source=pipeline.COLLECTION,
                method="Selected GEE image metadata",
                limitations=["Image is outside the requested observation period; no current water measurement was calculated"],
            ),
        }
        result["geometry"] = {
            **geometry_metadata,
            "measurement_scope": "NO_WATER_MEASUREMENT_STALE_IMAGERY",
        }
        result["decision_support"] = {
            "status": "STALE",
            "reason": result["reason"],
            "risk_available": False,
        }
        return result
    rgb = image.select(["B4", "B3", "B2"]).visualize(
        min=0, max=3000, gamma=1.2, forceRgbOutput=True
    ).clip(geometry)
    image_url = rgb.getThumbURL({"region": bounds, "dimensions": 512, "format": "png"})

    from satellite.ndwi_analysis import NDWIAnalyzer
    ndwi_analyzer = NDWIAnalyzer()
    # Pixel-level quality masking (Sentinel-2 SCL) before any NDWI / water
    # computation. On failure the image is used UNMASKED and quality_masking
    # reports the reason. A failed mask is not a valid live observation.
    masked_image, quality_masking = ndwi_analyzer.apply_quality_mask(image, lake_geometry)
    if quality_masking.get("status") != "APPLIED":
        result["status"] = "SATELLITE_PROCESSING_ERROR"
        result["reason"] = quality_masking.get(
            "reason", "Sentinel-2 quality masking was not applied"
        )
        result["satellite"] = {
            "status": "MASKING_FAILED",
            "region": region_key,
            "image_id": metadata.get("system:index"),
            "acquisition_time": acquisition_time,
            "quality_masking": quality_masking,
            "water_area": None,
        }
        result["decision_support"] = {
            "status": "INSUFFICIENT_DATA",
            "reason": result["reason"],
            "risk_available": False,
        }
        return merge_reliability_metadata(
            result,
            reliability.failure("DATA_QUALITY_MASKING", result["reason"]),
        )

    ndwi_image = ndwi_analyzer.calculate_ndwi(masked_image)
    water_mask = ndwi_analyzer.create_water_mask(ndwi_image)
    valid_pixel_mask = masked_image.select("B3").mask()
    candidate_detection = None
    multi_signal_identity = None
    if region_key == "Tsho_Rolpa_Nepal":
        candidate_detection = derive_gee_candidates(
            ndwi_image=ndwi_image,
            masked_image=masked_image,
            roi_geometry=lake_geometry,
            expected_center=geometry_center(lake_geometry),
            ndwi_threshold=ndwi_analyzer.ndwi_water_threshold,
            valid_pixel_fraction=quality_masking.get("valid_pixel_fraction"),
            quality_image=image,
            target_name=region["lake_name"],
        )
        reference_geometry, reference_metadata = get_authoritative_reference(region_key)
        if reference_geometry is not None:
            authoritative_validation = validate_authoritative_boundary(
                candidate_detection.get("selected_candidate") or {},
                reference_geometry,
                reference_metadata,
            )
        else:
            authoritative_validation = {
                "identity_status": IDENTITY_AMBIGUOUS,
                "reference_geometry_trust": reference_metadata.get("trust_status", "UNTRUSTED"),
                "reference_source": reference_metadata.get("source"),
                "measurement_authority": "WITHHELD",
                "reason": [reference_metadata.get(
                    "reason", "No verified authoritative reference geometry is configured"
                )],
            }
        multi_signal_identity = evaluate_multi_signal_identity(
            candidate_detection=candidate_detection,
            authoritative_validation=authoritative_validation,
            primary_provenance=provenance(
                DERIVED_FROM_REAL_DATA,
                source=pipeline.COLLECTION,
                method="Sentinel-2 candidate identity evidence",
            ),
        )
        single_observation = {
            "image_id": metadata.get("system:index"),
            "acquisition_time": acquisition_time,
            "candidate_detection": candidate_detection,
        }
        result["derived_candidate_measurements"] = (
            _derive_candidate_open_water_measurements(
                single_observation,
                {"ndwi": ndwi_image, "masked_image": masked_image},
                ndwi_analyzer,
                lake_geometry,
            )
        )
        result["evidence_lifecycle"] = build_evidence_lifecycle(
            observations=[single_observation],
            multi_signal_identity=multi_signal_identity,
            authoritative_validation=authoritative_validation,
            derived_candidate_measurements=[
                measurement for measurement in result["derived_candidate_measurements"]
                if measurement.get("status") == "DERIVED_CANDIDATE_OPEN_WATER"
            ],
        )
        result["authoritative_boundary_validation"] = authoritative_validation
        result["lake_likeness"] = assess_lake_likeness(
            candidate_detection.get("candidates", []),
        )
        if not multi_signal_identity.get("measurement_permitted"):
            result["status"] = IDENTITY_AMBIGUOUS
            result["reason"] = multi_signal_identity["reason"]
            result["multi_signal_identity"] = multi_signal_identity
            result["provenance"] = provenance(
                DERIVED_FROM_REAL_DATA,
                source=pipeline.COLLECTION,
                method="Multi-signal Sentinel-2 lake identity evaluation",
                limitations=multi_signal_identity["limitations"],
            )
            result["geometry"] = {
                **geometry_metadata,
                "search_area": bounds,
                "analysis_area": lake_geometry,
                "measurement_scope": "DERIVED_CANDIDATE_UNCERTAIN",
            }
            result["satellite"] = {
                "status": IDENTITY_AMBIGUOUS,
                "region": region_key,
                "image_id": metadata.get("system:index"),
                "acquisition_time": acquisition_time,
                "quality_masking": quality_masking,
                "candidate_detection": _public_candidate_detection(candidate_detection),
                "multi_signal_identity": multi_signal_identity,
                "water_area": None,
                "provenance": provenance(
                    DERIVED_FROM_REAL_DATA,
                    source=pipeline.COLLECTION,
                    method="Sentinel-2 candidate identity evidence",
                    limitations=multi_signal_identity["limitations"],
                ),
            }
            result["decision_support"] = {
                "status": IDENTITY_AMBIGUOUS,
                "reason": result["reason"],
                "risk_available": False,
            }
            return result
        if candidate_detection.get("identity_status") != IDENTITY_SUPPORTED:
            result["status"] = candidate_detection.get("identity_status", "IDENTITY_UNCERTAIN")
            result["reason"] = candidate_detection.get("reason", [])
            result["provenance"] = provenance(
                DERIVED_FROM_REAL_DATA,
                source=pipeline.COLLECTION,
                method="Real Sentinel-2 candidate water-body detection",
                limitations=["Candidate identity was not sufficiently supported for target-lake area publication"],
            )
            result["geometry"] = {
                **geometry_metadata,
                "search_area": bounds,
                "analysis_area": lake_geometry,
                "measurement_scope": "DERIVED_CANDIDATE_UNCERTAIN",
            }
            result["satellite"] = {
                "status": result["status"],
                "region": region_key,
                "image_id": metadata.get("system:index"),
                "acquisition_time": acquisition_time,
                "quality_masking": quality_masking,
                "candidate_detection": _public_candidate_detection(candidate_detection),
                "water_area": None,
                "provenance": provenance(
                    REAL_SATELLITE_DATA,
                    source=pipeline.COLLECTION,
                    method="Sentinel-2 candidate water-body detection",
                    limitations=["Candidate identity was not sufficiently supported for an observed area"],
                ),
            }
            result["decision_support"] = {
                "status": "IDENTITY_UNCERTAIN",
                "reason": result["reason"],
                "risk_available": False,
            }
            return result
        water_mask = candidate_detection["selected_mask"]
    water_area = ndwi_analyzer.calculate_water_area(
        water_mask,
        lake_geometry,
        pixel_area_sqm=100,
        valid_pixel_mask=valid_pixel_mask,
        scale=10 if region_key == "Tsho_Rolpa_Nepal" else 30,
    )
    if not isinstance(water_area, dict):
        result["status"] = "SATELLITE_PROCESSING_ERROR"
        result["reason"] = "Sentinel-2 water-area calculation failed"
        result["satellite"] = {
            "status": "PROCESSING_FAILED",
            "region": region_key,
            "image_id": metadata.get("system:index"),
            "acquisition_time": acquisition_time,
            "quality_masking": quality_masking,
            "water_area": None,
        }
        result["decision_support"] = {
            "status": "INSUFFICIENT_DATA",
            "reason": result["reason"],
            "risk_available": False,
        }
        return merge_reliability_metadata(
            result,
            reliability.failure("WATER_AREA_PROCESSING", result["reason"]),
        )
    if water_area.get("status") == "NO_VALID_PIXELS":
        result["status"] = "NO_VALID_PIXELS"
        result["reason"] = "No valid Sentinel-2 pixels remained after quality masking"
        result["satellite"] = {
            "status": "NO_VALID_PIXELS",
            "region": region_key,
            "image_id": metadata.get("system:index"),
            "acquisition_time": acquisition_time,
            "quality_masking": quality_masking,
            "water_area": water_area,
        }
        result["decision_support"] = {
            "status": "INSUFFICIENT_DATA",
            "reason": result["reason"],
            "risk_available": False,
        }
        return merge_reliability_metadata(
            result,
            reliability.failure("WATER_AREA_VALIDITY", result["reason"]),
        )

    baseline = {
        "status": "INSUFFICIENT_HISTORICAL_DATA",
        "reason": "No sufficient same-calendar-month historical Sentinel-2 observations were found",
        "observations": [],
    }
    seasonal_comparison = None
    historical_observations = []
    baseline_candidate_detections = []
    current_acquisition_ms = metadata.get("system:time_start")
    if current_acquisition_ms:
        current_datetime = datetime.fromtimestamp(current_acquisition_ms / 1000, timezone.utc)
        historical_start = current_datetime - timedelta(days=5 * 365)
        historical_end = current_datetime - timedelta(days=5)
        baseline_collection = (
            ee.ImageCollection(pipeline.COLLECTION)
            .filterBounds(geometry)
            .filterDate(historical_start.strftime("%Y-%m-%d"), historical_end.strftime("%Y-%m-%d"))
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 50))
            .filter(ee.Filter.calendarRange(current_datetime.month, current_datetime.month, "month"))
            .sort("system:time_start")
        )
        if baseline_collection.size().getInfo() > 0:
            baseline_covered = pipeline.filter_collection_covering(
                baseline_collection, lake_geometry
            )
            baseline_collection = baseline_covered
        historical_count = baseline_collection.size().getInfo()
        historical_limit = min(historical_count, 24)
        historical_images = baseline_collection.toList(historical_limit)
        for historical_index in range(historical_limit):
            baseline_image = ee.Image(historical_images.get(historical_index))
            baseline_metadata = baseline_image.getInfo().get("properties", {})
            baseline_masked, baseline_quality_masking = ndwi_analyzer.apply_quality_mask(
                baseline_image, lake_geometry
            )
            baseline_ms = baseline_metadata.get("system:time_start")
            historical_record = {
                "image_id": baseline_metadata.get("system:index"),
                "acquisition_time": datetime.fromtimestamp(baseline_ms / 1000, timezone.utc).isoformat() if baseline_ms else None,
                "cloud_cover_percent": baseline_metadata.get("CLOUDY_PIXEL_PERCENTAGE"),
                "quality_masking": baseline_quality_masking,
                "provenance": provenance(
                    REAL_SATELLITE_DATA,
                    source=pipeline.COLLECTION,
                    method="Historical same-calendar-month Sentinel-2 acquisition",
                ),
            }
            if baseline_quality_masking.get("status") != "APPLIED":
                historical_record["status"] = "MASKING_FAILED"
            else:
                baseline_ndwi = ndwi_analyzer.calculate_ndwi(baseline_masked)
                baseline_mask = ndwi_analyzer.create_water_mask(baseline_ndwi)
                baseline_valid_pixel_mask = baseline_masked.select("B3").mask()
                historical_candidate_detection = None
                if region_key == "Tsho_Rolpa_Nepal":
                    historical_candidate_detection = derive_gee_candidates(
                        ndwi_image=baseline_ndwi,
                        masked_image=baseline_masked,
                        roi_geometry=lake_geometry,
                        expected_center=geometry_center(lake_geometry),
                        ndwi_threshold=ndwi_analyzer.ndwi_water_threshold,
                        valid_pixel_fraction=baseline_quality_masking.get("valid_pixel_fraction"),
                        quality_image=baseline_image,
                        target_name=region["lake_name"],
                    )
                    baseline_candidate_detections.append(
                        _public_candidate_detection(historical_candidate_detection)
                    )
                    if historical_candidate_detection.get("identity_status") == IDENTITY_SUPPORTED:
                        baseline_mask = historical_candidate_detection["selected_mask"]
                        historical_record["boundary"] = (
                            historical_candidate_detection.get("selected_candidate") or {}
                        ).get("boundary")
                    else:
                        historical_record["status"] = "IDENTITY_UNCERTAIN"
                baseline_area = ndwi_analyzer.calculate_water_area(
                    baseline_mask, lake_geometry,
                    valid_pixel_mask=baseline_valid_pixel_mask,
                    scale=10 if region_key == "Tsho_Rolpa_Nepal" else 30,
                )
                historical_record["water_area"] = baseline_area
                if historical_record.get("status") != "IDENTITY_UNCERTAIN":
                    historical_record["status"] = baseline_area.get("status", "SUCCESS")
                else:
                    historical_record["water_area"] = None
                if historical_record["status"] == "SUCCESS":
                    historical_record["water_area_sqkm"] = baseline_area.get("area_sqkm")
            historical_observations.append(historical_record)

        current_baseline_observation = {
            "acquisition_time": acquisition_time,
            "water_area_sqkm": (water_area or {}).get("area_sqkm"),
            "status": water_area.get("status") if isinstance(water_area, dict) else "INVALID",
        }
        seasonal_comparison = evaluate_against_seasonal_baseline(
            current_baseline_observation,
            historical_observations,
            minimum_observations=3,
        )
        baseline = seasonal_comparison["baseline"]
        baseline["historical_query"] = {
            "start": historical_start.isoformat(),
            "end": historical_end.isoformat(),
            "candidate_count": historical_count,
            "selected_count": historical_limit,
        }
        baseline["candidate_detections"] = baseline_candidate_detections
    current_area_sqkm = (water_area or {}).get("area_sqkm")
    current_area_valid = isinstance(current_area_sqkm, (int, float))
    baseline_area_valid = bool(
        seasonal_comparison and seasonal_comparison.get("status") == "VALID"
    )
    cloud_values = [
        value for value in (
            metadata.get("CLOUDY_PIXEL_PERCENTAGE"),
            *[
                item.get("cloud_cover_percent")
                for item in (baseline.get("observations") or [])
            ],
        ) if isinstance(value, (int, float))
    ]
    cloud_confidence = (
        sum(max(0.0, min(100.0, 100.0 - value)) / 100.0 for value in cloud_values) / len(cloud_values)
        if cloud_values else 0.0
    )
    comparison_valid = current_area_valid and baseline_area_valid
    data_quality = {
        "confidence": cloud_confidence if comparison_valid else 0.0,
        "cloud_confidence": cloud_confidence,
        "current_cloud_cover_percent": metadata.get("CLOUDY_PIXEL_PERCENTAGE"),
        "baseline_cloud_cover_percent": [
            item.get("cloud_cover_percent")
            for item in (baseline.get("observations") or [])
            if isinstance(item.get("cloud_cover_percent"), (int, float))
        ],
        "current_water_area_valid": current_area_valid,
        "baseline_water_area_valid": baseline_area_valid,
        "comparison_status": "VALID" if comparison_valid else "NOT_AVAILABLE",
        "baseline_observation_count": baseline.get("observation_count", 0),
        "quality_mask_status": quality_masking.get("status"),
        "valid_pixel_fraction": quality_masking.get("valid_pixel_fraction")
    }
    analysis_geometry = ee.Geometry(lake_geometry)
    ndwi_stats = ndwi_image.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=analysis_geometry, scale=30,
        maxPixels=10_000_000, bestEffort=True
    ).getInfo()
    ndwi_value = next(iter(ndwi_stats.values()), None) if ndwi_stats else None

    ndsi = image.select("B3").subtract(image.select("B11")).divide(
        image.select("B3").add(image.select("B11"))
    )
    ndsi_stats = ndsi.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=analysis_geometry , scale=20,
        maxPixels=10_000_000, bestEffort=True
    ).getInfo()
    ndsi_value = next(iter(ndsi_stats.values()), None) if ndsi_stats else None

    satellite_observation = {
        "region": region_key,
        "satellite": "Sentinel-2",
        "collection": pipeline.COLLECTION,
        "image_id": metadata.get("system:index"),
        "acquisition_time": acquisition_time,
        "cloud_cover_percent": metadata.get("CLOUDY_PIXEL_PERCENTAGE"),
        "image_url": image_url,
        "ndwi_value": ndwi_value,
        "ndwi_threshold": {
            "value": ndwi_analyzer.ndwi_water_threshold,
            "validated": False,
            "note": "Generic McFeeters (1996) water threshold; NOT calibrated for Himalayan glacial lakes"
        },
        "quality_masking": quality_masking,
        "water_area": water_area,
        "candidate_detection": (
            _public_candidate_detection(candidate_detection)
        ),
        "multi_signal_identity": multi_signal_identity,
        "baseline_candidate_detection": baseline.get("candidate_detections", []),
        "seasonal_baseline": baseline,
        "seasonal_comparison": seasonal_comparison,
        "baseline": baseline,
        "data_quality": data_quality,
        "snow_ice": {
            "status": "DERIVED",
            "ndsi_mean": ndsi_value,
            "note": "NDSI-based snow/ice classification signal; not a glacier boundary or GLOF proof"
        },
        "status": "SUCCESS",
    }
    result["satellite"] = satellite_observation
    result["provenance"] = provenance(
        DERIVED_FROM_REAL_DATA,
        source="Google Earth Engine Sentinel-2 SR Harmonized",
        method="SCL-masked B3/B8 NDWI threshold and pixel-area reduction",
        limitations=(
            ["NDWI threshold is not calibrated for Himalayan glacial lakes"]
            + ([] if geometry_metadata["status"] in {"VALIDATED", "AUTHORITATIVE"} else [
                "Analysis uses an approximate ROI rather than an authoritative lake boundary"
            ])
        ),
    )
    result["geometry"] = {
        **geometry_metadata,
        "search_area": bounds,
        "analysis_area": lake_geometry,
        "measurement_scope": "LAKE_WATER_EXTENT" if geometry_metadata["status"] in {"VALIDATED", "AUTHORITATIVE"} else "DERIVED_CANDIDATE_WATER_EXTENT_IN_APPROXIMATE_ROI",
    }
    if candidate_detection and candidate_detection.get("selected_candidate"):
        result["geometry"]["observed_boundary"] = candidate_detection["selected_candidate"]["boundary"]
        result["geometry"]["observed_boundary_status"] = "DERIVED_CANDIDATE"
    result["satellite"]["provenance"] = provenance(
        REAL_SATELLITE_DATA,
        source=pipeline.COLLECTION,
        method="Selected GEE image metadata and pixels",
        limitations=([] if geometry_metadata["status"] in {"VALIDATED", "AUTHORITATIVE"} else [
            "Image pixels are real; target-lake identity is not verified by a bundled lake polygon"
        ]),
    )
    result["satellite"]["water_area"]["measurement_scope"] = (
        "LAKE_WATER_EXTENT" if geometry_metadata["status"] in {"VALIDATED", "AUTHORITATIVE"} else "DERIVED_CANDIDATE_WATER_EXTENT_IN_APPROXIMATE_ROI"
    )
    result["satellite"]["water_area"]["provenance"] = provenance(
        DERIVED_FROM_REAL_DATA,
        source=metadata.get("system:index"),
        method="ee.Image.pixelArea() reduced over the configured lake geometry",
        limitations=([] if geometry_metadata["status"] in {"VALIDATED", "AUTHORITATIVE"} else [
            "This is not an authoritative lake-area measurement"
        ]),
    )
    result["satellite_change_evidence"] = evaluate_contextual_change(
        {
            "water_area_sqkm": current_area_sqkm,
            "boundary": (
                (candidate_detection or {}).get("selected_candidate") or {}
            ).get("boundary"),
            "identity_status": (
                (candidate_detection or {}).get("identity_status")
                or ((candidate_detection or {}).get("selected_candidate") or {})
                .get("identity_status")
            ),
            "cloud_cover_percent": metadata.get("CLOUDY_PIXEL_PERCENTAGE"),
            "quality_masking": quality_masking,
            "data_quality": data_quality,
            "provenance": result["satellite"]["provenance"],
            "assumptions": [
                "Contextual change evidence does not establish a GLOF event or probability"
            ],
            "limitations": result["provenance"].get("limitations", []),
        },
        seasonal_comparison or {"status": "NOT_AVAILABLE"},
        temporal_evidence=None,
    )
    result["satellite_change_evidence"]["region"] = region_key

    engine = RiskEngine()
    sensor_readings = None
    sensor_signal = None
    if mode == "simulation":
        network = SensorNetwork(region_key)
        network.add_vibration_sensor("VIB-001")
        network.add_water_level_sensor("WATER-001")
        network.add_rainfall_sensor("RF-001")
        sensor_readings = network.read_all_sensors()
        flattened = {
            reading["sensor_type"]: reading["value"]
            for reading in sensor_readings["sensors"].values()
        }
        rainfall_reading = sensor_readings["sensors"].get("RF-001")
        sensor_readings["source"] = "virtual_sensor_simulation"
        sensor_readings["simulated"] = True
        sensor_readings["note"] = "Simulated virtual sensor readings - NOT real measurements"
        sensor_signal = engine.calculate_sensor_signal({
            "vibration_cmps": flattened.get("vibration"),
            "water_level_cm": flattened.get("water_level"),
            "rainfall_mmph": rainfall_reading
        })

    ai_result = {
        "status": "NOT_AVAILABLE",
        "signal": 0.0,
        "reason": "Generic YOLOv8n analysis is unavailable for this satellite image",
        "note": "Generic YOLOv8n is not a GLOF-domain signal",
    }
    try:
        # Use local cache to avoid URL access issues
        image_cache = get_image_cache()
        image_id = metadata.get("system:index", "unknown")
        
        # Try to get cached image or download it
        local_image_path, cache_success, cache_metadata = image_cache.download_and_cache_image(
            image_url=image_url,
            region_key=region_key,
            image_id=image_id,
            band_config="rgb"
        )
        
        if local_image_path and cache_success:
            detector = YOLOv8Detector(model_name="yolov8n.pt", confidence_threshold=0.5)
            detections = detector.detect_objects(local_image_path)
            
            # Keep COCO detections for transparency only. Do not use calculate_ai_signal()
            # here: generic people/vehicles/etc. must not raise GLOF risk.
            ai_result = {
                "status": "NO_DOMAIN_SIGNAL",
                "model": "yolov8n.pt",
                "detector_type": "generic_object_detector",
                "detection_count": len(detections),
                "detections": [detection.to_dict() for detection in detections],
                "signal": glof_ai_signal_for_risk("NO_DOMAIN_SIGNAL"),
                "note": "Generic detections are not glacial-lake or GLOF detections; no domain-specific AI signal is inferred",
                "image_source": cache_metadata.get("source", "unknown"),
                "cache_hit": cache_metadata.get("cache_hit", False)
            }
        else:
            ai_result["reason"] = f"Image caching failed: {cache_metadata.get('error', 'Unknown error')}"
            ai_result["signal"] = glof_ai_signal_for_risk(ai_result["status"])
            
    except Exception as exc:
        ai_result["reason"] = f"Generic YOLOv8n analysis unavailable: {exc}"
        ai_result["signal"] = glof_ai_signal_for_risk(ai_result["status"])

    ai_signal = glof_ai_signal_for_risk(ai_result["status"])

    satellite_signal_inputs = {
        "ndwi_value": ndwi_value or 0,
        "current_area_sqkm": current_area_sqkm or 0,
        "cloud_cover_percent": metadata.get("CLOUDY_PIXEL_PERCENTAGE", 0),
        "data_quality": data_quality
    }
    satellite_signal = engine.calculate_satellite_signal(satellite_signal_inputs)
    weather = result.get("weather") or {}
    weather_signal = weather.get("signal") if weather.get("status") == "SUCCESS" else None
    if mode == "monitoring" and isinstance(weather_signal, (int, float)):
        sensor_signal = weather_signal
        weather["used_for_risk_signal"] = True
        weather["risk_signal"] = weather_signal
    elif mode == "monitoring":
        weather["used_for_risk_signal"] = False
    previous_change = _previous_observation_change(
        ObservationStore(), region_key, current_area_sqkm
    )
    seasonal_baseline_mean = (
        ((seasonal_comparison or {}).get("baseline") or {})
        .get("statistics", {})
        .get("mean")
    )
    percent_change = (seasonal_comparison or {}).get("deviation_percentage")
    result["satellite_change"] = {
        "region": region_key,
        "current_area_sqkm": current_area_sqkm,
        "previous_area_sqkm": previous_change["previous_area_sqkm"],
        "previous_observation_id": previous_change["previous_observation_id"],
        "previous_acquisition_time": previous_change["previous_acquisition_time"],
        "previous_observation_percent_change": previous_change[
            "previous_observation_percent_change"
        ],
        "seasonal_baseline_mean_sqkm": seasonal_baseline_mean,
        "seasonal_baseline": (seasonal_comparison or {}).get("baseline"),
        "percent_change": percent_change,
        "trend": previous_change["trend"],
        "satellite_risk_signal": satellite_signal,
        "data_quality_confidence": data_quality["confidence"],
        "status": "CALCULATED" if comparison_valid or previous_change["trend"] else "NOT_AVAILABLE",
        "note": "Previous-observation change is separate from the seasonal historical baseline"
    }
    result["sensors"] = sensor_readings or {
        "status": "NOT_RUN",
        "note": "Virtual sensors run only in simulation mode",
        "simulated": True,
    }
    result["ai"] = ai_result
    result["decision_support"] = {
        "status": "PROTOTYPE_ASSESSMENT",
        "reason": "RiskEngine assessment is available for this processed observation",
        "risk_available": True,
        "risk_interpretation": "Prototype decision support; not a validated GLOF probability",
    }
    _attach_risk_and_history(
        result,
        engine,
        satellite_signal,
        ai_signal,
        sensor_signal,
        region_key,
    )
    result["risk"]["signal_sources"] = {
        "satellite": "Sentinel-2 NDWI and water-area evidence",
        "ai": "Generic YOLO is not a GLOF-domain signal",
        "sensor": "Open-Meteo rainfall" if weather.get("used_for_risk_signal") else "Unavailable",
    }
    result["risk_change_explanation"] = _risk_change_explanation(
        ObservationStore(), region_key, result
    )
    _validate_nested_region_identity(result, region_key)
    result["data_confidence"] = _data_confidence_summary(result)
    result["status"] = "SUCCESS"
    result["validity_status"] = "VALID"
    return result


def run_integrated_monitoring(region_key, start_date=None, end_date=None, mode="monitoring"):
    """Run monitoring through the synchronous seven-stage execution manager."""

    def imagery_acquisition(*_args):
        _ = _args
        try:
            observation = _run_integrated_monitoring(
                region_key, start_date, end_date, mode
            )
        except Exception as exc:
            return {"ok": False, "status": "UNAVAILABLE", "reason": str(exc)}
        if not isinstance(observation, dict):
            return {"ok": False, "status": "UNAVAILABLE", "reason": "Monitoring returned no observation envelope"}
        if region_key in HIMALAYAN_REGIONS:
            try:
                validate_observation(observation, region_key)
                _validate_nested_region_identity(observation, region_key)
            except ValueError as exc:
                return {"ok": False, "status": "REGION_INTEGRITY_ERROR", "reason": str(exc)}
        if observation.get("validity_status") == "UNAVAILABLE":
            return {"ok": False, "status": "UNAVAILABLE", "reason": observation.get("reason", "Observation is unavailable")}
        if observation.get("status") in {
            "ERROR", "NO_SUITABLE_IMAGERY", "STALE_IMAGERY",
            "SATELLITE_PROCESSING_ERROR", "NO_VALID_PIXELS",
        }:
            return {"ok": False, "status": observation.get("status"), "reason": observation.get("reason", "Imagery acquisition failed")}
        return {"ok": True, "status": "VALID", "context": {"observation": observation}}

    def quality_masking(context):
        observation = context["observation"]
        satellite = observation.get("satellite") or {}
        quality = satellite.get("quality_masking") or {}
        if not quality:
            return {"ok": True, "status": "NOT_REPORTED"}
        if quality.get("status") != "APPLIED":
            return {"ok": False, "status": "UNAVAILABLE", "reason": "Satellite quality masking was not applied"}
        return {"ok": True, "status": "VALID"}

    def timeline_validation(context):
        observation = context["observation"]
        if observation.get("status") == "STALE_IMAGERY":
            return {"ok": False, "status": "STALE_IMAGERY", "reason": "Acquisition is outside the requested observation period"}
        satellite = observation.get("satellite") or {}
        if not satellite.get("acquisition_time"):
            return {"ok": False, "status": "UNAVAILABLE", "reason": "Acquisition timestamp is unavailable"}
        return {"ok": True, "status": "VALID"}

    def observation_storage(context):
        observation = context["observation"]
        try:
            record = ObservationStore().save(observation)
        except Exception as exc:
            return {"ok": False, "status": "UNAVAILABLE", "reason": f"Observation could not be persisted: {exc}"}
        observation = deepcopy(observation)
        observation["persistence"] = {
            "status": "SAVED",
            "observation_id": record["observation_id"],
            "recorded_at": record["recorded_at"],
        }
        observation["observation_id"] = record["observation_id"]
        return {"ok": True, "status": "SAVED", "context": {"observation": observation}}

    def seasonal_baseline_comparison(context):
        observation = context["observation"]
        seasonal = (observation.get("satellite") or {}).get("seasonal_comparison")
        if not isinstance(seasonal, dict) or seasonal.get("status") != "VALID":
            return {"ok": False, "status": "INSUFFICIENT_DATA", "reason": "Seasonal baseline comparison is unavailable or insufficient"}
        return {"ok": True, "status": "VALID"}

    def risk_assessment(context):
        observation = context["observation"]
        if not isinstance(observation.get("risk"), dict):
            return {"ok": False, "status": "INSUFFICIENT_DATA", "reason": "Risk assessment is unavailable"}
        risk = observation["risk"]
        if risk.get("decision_support_status") == "INSUFFICIENT_DATA" or risk.get("assessment_status") in {"INSUFFICIENT_CONFIDENCE", "LIMITED_CONFIDENCE"}:
            return {"ok": False, "status": "INSUFFICIENT_DATA", "reason": "Risk assessment confidence is insufficient"}
        return {"ok": True, "status": "VALID"}

    def early_warning_status(context):
        observation = context["observation"]
        status_result = evaluate_early_warning_status(observation)
        updated_observation = deepcopy(observation)
        updated_observation["early_warning_status"] = status_result
        try:
            historical = ObservationStore().list(observation.get("region"), limit=500)
            current_id = observation.get("observation_id")
            historical = [
                record for record in historical
                if record.get("observation_id") != current_id
            ]
            updated_observation["alert_confirmation"] = evaluate_warning_confirmation(
                updated_observation, historical
            )
            updated_observation["alert_confirmation"]["region"] = observation.get("region")
        except Exception as exc:
            updated_observation["alert_confirmation"] = {
                "region": observation.get("region"),
                "state": "NO_ACTIVE_WARNING",
                "warning_status": status_result.get("status"),
                "confirmed": False,
                "persistent": False,
                "reason": f"Confirmation history is unavailable: {exc}",
            }
        updated_observation["human_warning"] = build_human_warning(
            updated_observation, status_result
        )
        if updated_observation.get("observation_id"):
            try:
                ObservationStore().update_observation_payload(
                    updated_observation["observation_id"],
                    {
                        "early_warning_status": updated_observation["early_warning_status"],
                        "alert_confirmation": updated_observation["alert_confirmation"],
                        "human_warning": updated_observation["human_warning"],
                    },
                )
            except Exception:
                pass
        if status_result.get("status") == INSUFFICIENT_DATA:
            return {
                "ok": False,
                "status": INSUFFICIENT_DATA,
                "reason": "; ".join(status_result.get("reasons", [])),
                "context": {
                    "observation": updated_observation,
                    "early_warning_status": status_result,
                },
            }
        return {"ok": True, "status": status_result["status"], "context": {"observation": updated_observation, "early_warning_status": status_result}}

    manager = MonitoringExecutionManager({
        "IMAGERY_ACQUISITION": imagery_acquisition,
        "DATA_QUALITY_MASKING": quality_masking,
        "ACQUISITION_TIMELINE_VALIDATION": timeline_validation,
        "OBSERVATION_STORAGE": observation_storage,
        "SEASONAL_BASELINE_COMPARISON": seasonal_baseline_comparison,
        "RISK_ASSESSMENT": risk_assessment,
        "EARLY_WARNING_STATUS": early_warning_status,
    })
    execution = manager.run()
    execution_summary = {
        key: value for key, value in execution.items() if key != "context"
    }
    observation = execution.get("context", {}).get("observation")
    if execution["job_status"] == "SUCCEEDED":
        _validate_nested_region_identity(observation, region_key)
        observation["execution"] = execution_summary
        return observation
    if isinstance(observation, dict):
        observation["execution"] = execution_summary
        observation["status"] = "ERROR"
        observation["validity_status"] = "UNAVAILABLE"
        observation["reason"] = execution["failure_reason"]
        observation["decision_support"] = {
            "status": INSUFFICIENT_DATA,
            "reason": execution["failure_reason"],
            "risk_available": False,
        }
        return observation
    result = _integrated_result_skeleton(
        region_key, status="ERROR", mode=mode, reason=execution["failure_reason"]
    )
    result["execution"] = execution_summary
    result["status"] = "ERROR"
    result["validity_status"] = "UNAVAILABLE"
    return result


def _derive_candidate_open_water_measurements(
    observation, internal, analyzer, region_geometry
):
    """Measure eligible candidate masks without asserting named-lake identity."""
    candidates = (observation.get("candidate_detection") or {}).get("candidates", [])
    measurements = []
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        boundary = candidate.get("boundary")
        eligibility = candidate.get("temporal_eligibility") or candidate_temporal_eligibility(candidate)
        measurement = {
            "status": "UNAVAILABLE",
            "candidate_id": candidate_id,
            "area_sqkm": None,
            "boundary": boundary,
            "image_id": observation.get("image_id"),
            "acquisition_time": observation.get("acquisition_time"),
            "measurement_scope": "DERIVED_CANDIDATE_OPEN_WATER",
            "provenance": provenance(
                UNAVAILABLE,
                source=observation.get("image_id"),
                method="SCL-masked Sentinel-2 candidate water mask",
                limitations=[
                    "Candidate measurement does not establish named-lake identity",
                    "Candidate measurement is not an authoritative lake area",
                ],
            ),
        }
        if not eligibility.get("eligible"):
            measurement["reason"] = eligibility.get("reasons")
            measurements.append(measurement)
            continue
        if internal is None or not boundary:
            measurement["reason"] = "Candidate image or boundary is unavailable"
            measurements.append(measurement)
            continue
        try:
            import ee

            candidate_geometry = ee.Geometry(boundary)
            candidate_mask = internal["ndwi"].gt(
                analyzer.ndwi_water_threshold
            ).selfMask().clip(candidate_geometry)
            valid_pixel_mask = internal["masked_image"].select("B3").mask().clip(
                candidate_geometry
            )
            area = analyzer.calculate_water_area(
                candidate_mask,
                boundary,
                valid_pixel_mask=valid_pixel_mask,
                scale=10,
            )
            if isinstance(area, dict) and area.get("status") == "SUCCESS":
                measurement.update({
                    "status": "DERIVED_CANDIDATE_OPEN_WATER",
                    "area_sqkm": area.get("area_sqkm"),
                    "area_sqm": area.get("area_sqm"),
                    "pixel_area_source": area.get("pixel_area_source"),
                    "provenance": provenance(
                        DERIVED_FROM_REAL_DATA,
                        source=observation.get("image_id"),
                        method="SCL-masked Sentinel-2 candidate water mask and ee.Image.pixelArea()",
                        limitations=[
                            "Observed open-water extent of a derived candidate only",
                            "Does not establish named-lake identity or authoritative lake area",
                        ],
                    ),
                })
            else:
                measurement["reason"] = (area or {}).get(
                    "status", "Candidate water-area measurement was unavailable"
                )
        except Exception as exc:
            measurement["reason"] = f"Candidate water-area measurement failed: {exc}"
        measurements.append(measurement)
    return measurements


def _run_temporal_evidence(region_key, start_date, end_date, max_observations=6):
    """Evaluate repeatable real-satellite candidates for one configured region."""
    region = get_region_info(region_key)
    if region is None:
        raise ValueError(f"Region '{region_key}' not found")
    lake_geometry, geometry_metadata = get_lake_geometry(region_key)
    if lake_geometry is None:
        raise ValueError(f"Region '{region_key}' has no analysis geometry")
    start_date, end_date = _temporal_date_range(start_date, end_date)
    if not isinstance(max_observations, int) or not 1 <= max_observations <= 12:
        raise ValueError("max_observations must be an integer from 1 to 12")

    pipeline = initialize_gee_pipeline()
    if pipeline is None:
        return {
            "status": "UNAVAILABLE",
            "validity_status": "UNAVAILABLE",
            "region": region_key,
            "reason": "Google Earth Engine authentication failed",
            "observations": [],
        }

    import ee
    search_geometry = get_region_bounds(region_key)
    discovery_geometry = _temporal_discovery_geometry(
        search_geometry, lake_geometry, geometry_metadata
    )
    discovery_expected_center = (
        geometry_center(lake_geometry)
        if geometry_metadata.get("status") in {"VALIDATED", "AUTHORITATIVE", "TRUSTED"}
        else None
    )
    collection = (
        ee.ImageCollection(pipeline.COLLECTION)
        .filterBounds(ee.Geometry(search_geometry))
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
    )
    collection = pipeline.filter_collection_covering(collection, discovery_geometry).sort("system:time_start")
    total = collection.size().getInfo()
    acquisition_diagnostics = {
        "collection": pipeline.COLLECTION,
        "requested_date_range": {"start": start_date, "end": end_date},
        "cloud_cover_limit": 60,
        "coverage_verified": True,
        "available_acquisitions": total,
        "selected_acquisitions": 0,
        "omitted_acquisitions": max(total - max_observations, 0) if total else 0,
        "observations": [],
    }
    if not total:
        return {
            "status": "NO_SUITABLE_IMAGERY",
            "region": region_key,
            "requested_date_range": {"start": start_date, "end": end_date},
            "observations": [],
            "acquisition_diagnostics": acquisition_diagnostics,
            "temporal_evidence": assess_target_identity(
                {"tracks": []}, geometry_center(lake_geometry), region["lake_name"]
            ),
        }

    indices = _temporal_acquisition_indices(total, max_observations)
    acquisition_diagnostics["selected_acquisitions"] = len(indices)
    image_list = collection.toList(total)
    observations = []
    internal_observations = {}
    analyzer = None
    terrain_image = None
    try:
        terrain_image = ee.Image("COPERNICUS/DEM/GLO-30").select("DEM")
    except Exception:
        terrain_image = None
    for index in indices:
        image = ee.Image(image_list.get(index))
        metadata = image.getInfo().get("properties", {})
        acquisition_ms = metadata.get("system:time_start")
        acquisition_time = datetime.fromtimestamp(acquisition_ms / 1000, timezone.utc).isoformat() if acquisition_ms else None
        from satellite.ndwi_analysis import NDWIAnalyzer
        analyzer = analyzer or NDWIAnalyzer()
        masked_image, quality = analyzer.apply_quality_mask(image, discovery_geometry)
        observation = {
            "image_id": metadata.get("system:index"),
            "acquisition_time": acquisition_time,
            "cloud_cover_percent": metadata.get("CLOUDY_PIXEL_PERCENTAGE"),
            "quality": quality,
            "candidate_detection": None,
        }
        if not _acquisition_is_in_requested_range(acquisition_ms, start_date, end_date):
            observation["status"] = "STALE_IMAGERY"
            observation["reason"] = "Acquisition is outside the requested observation period"
        elif quality.get("status") == "APPLIED":
            ndwi = analyzer.calculate_ndwi(masked_image)
            detection = derive_gee_candidates(
                ndwi, masked_image, discovery_geometry, discovery_expected_center,
                analyzer.ndwi_water_threshold,
                quality.get("valid_pixel_fraction"), quality_image=image,
                target_name=region["lake_name"],
                spectral_image=image,
                terrain_image=terrain_image,
            )
            observation["candidate_detection"] = _public_candidate_detection(detection)
            if not detection.get("candidates"):
                observation["status"] = "NO_WATER_CANDIDATES"
                observation["reason"] = detection.get(
                    "reason", ["No connected water candidate was produced"]
                )
            internal_observations[metadata.get("system:index")] = {
                "image": image,
                "masked_image": masked_image,
                "ndwi": ndwi,
                "quality": quality,
            }
        else:
            observation["status"] = "INSUFFICIENT_QUALITY"
            observation["reason"] = quality.get(
                "reason", "Sentinel-2 quality masking was not applied"
            )
        observations.append(observation)
        acquisition_diagnostics["observations"].append({
            "image_id": observation["image_id"],
            "acquisition_time": observation["acquisition_time"],
            "status": observation.get("status", "QUALITY_APPLIED"),
            "cloud_cover_percent": observation["cloud_cover_percent"],
            "valid_pixel_fraction": quality.get("valid_pixel_fraction"),
            "candidate_count": len(
                (observation.get("candidate_detection") or {}).get("candidates", [])
            ),
        })

    temporal_observations = [
        {
            "image_id": item["image_id"],
            "acquisition_time": item["acquisition_time"],
            "status": item.get("status", "QUALITY_APPLIED"),
            "reason": item.get("reason"),
            "candidates": (item.get("candidate_detection") or {}).get("candidates", []),
        }
        for item in observations
    ]
    tracks = build_temporal_tracks(temporal_observations)
    for observation in observations:
        candidates = (observation.get("candidate_detection") or {}).get("candidates", [])
        eligible = [
            candidate for candidate in candidates
            if candidate.get("temporal_eligibility", {}).get("eligible")
        ]
        observation["temporal_evidence_status"] = (
            "USABLE" if eligible else "DEGRADED_OR_EXCLUDED"
        )
        observation["temporal_eligible_candidate_count"] = len(eligible)
    temporal = assess_target_identity(
        tracks,
        geometry_center(lake_geometry),
        target_name=region["lake_name"],
    )
    current_observation = next(
        (
            observation for observation in reversed(observations)
            if (observation.get("candidate_detection") or {}).get("candidates")
        ),
        None,
    )
    latest_candidates = (
        (current_observation.get("candidate_detection") or {}).get("candidates", [])
        if current_observation else []
    )
    current_internal = (
        internal_observations.get(current_observation.get("image_id"))
        if current_observation else None
    )
    derived_candidate_measurements = _derive_candidate_open_water_measurements(
        current_observation,
        current_internal,
        analyzer,
        lake_geometry,
    ) if current_observation and analyzer else []
    temporal["identity_association"] = associate_temporal_identity(
        latest_candidates,
        [observation for observation in observations if observation is not current_observation],
    )
    latest_detection = current_observation.get("candidate_detection") if current_observation else None
    reference_geometry, reference_metadata = get_authoritative_reference(region_key)
    authoritative_validation = None
    if reference_geometry is not None and latest_detection:
        selected_candidate = latest_detection.get("selected_candidate") or {}
        authoritative_validation = validate_authoritative_boundary(
            selected_candidate,
            reference_geometry,
            reference_metadata,
            temporal_evidence=temporal,
        )
    else:
        authoritative_validation = {
            "identity_status": IDENTITY_AMBIGUOUS,
            "reference_geometry_trust": reference_metadata.get("trust_status", "UNTRUSTED"),
            "reference_source": reference_metadata.get("source"),
            "measurement_authority": "WITHHELD",
            "reason": [reference_metadata.get(
                "reason", "No verified authoritative reference geometry is configured"
            )],
        }
    multi_signal_identity = evaluate_multi_signal_identity(
        temporal_evidence=temporal,
        candidate_detection=latest_detection,
        authoritative_validation=authoritative_validation,
        primary_provenance=provenance(
            DERIVED_FROM_REAL_DATA,
            source=pipeline.COLLECTION,
            method="Temporal Sentinel-2 candidate identity evidence",
        ),
    )
    independent_satellite_data = query_landsat_availability(
        discovery_geometry, start_date, end_date
    )
    observed_measurement = {
        "status": "UNAVAILABLE",
        "area_sqkm": None,
        "boundary": None,
        "provenance": provenance(
            UNAVAILABLE,
            source="Temporal identity gate",
            method="Area withheld unless one target track is uniquely supported",
        ),
    }
    if (
        temporal.get("identity_status") == "IDENTITY_SUPPORTED"
        and multi_signal_identity.get("measurement_permitted")
    ):
        supported_tracks = [
            track for track in temporal.get("tracks", [])
            if track.get("observation_count", 0) >= temporal.get("minimum_observations", 3)
            and track.get("distance_to_expected_center_km", 999) <= 3.0
        ]
        if len(supported_tracks) == 1 and supported_tracks[0].get("observations"):
            latest = supported_tracks[0]["observations"][-1]
            internal = internal_observations.get(latest.get("image_id"))
            if internal and latest.get("boundary"):
                import ee
                candidate_mask = internal["ndwi"].gt(analyzer.ndwi_water_threshold).selfMask().clip(
                    ee.Geometry(latest["boundary"])
                )
                area = analyzer.calculate_water_area(
                    candidate_mask,
                    lake_geometry,
                    valid_pixel_mask=internal["masked_image"].select("B3").mask(),
                    scale=10,
                )
                if can_publish_observed_area(
                    temporal.get("identity_status"), area, latest.get("boundary")
                ):
                    observed_measurement = {
                        "status": "SUPPORTED_SATELLITE_OBSERVED_OPEN_WATER",
                        "area_sqkm": area.get("area_sqkm"),
                        "boundary": latest["boundary"],
                        "image_id": latest.get("image_id"),
                        "acquisition_time": latest.get("acquisition_time"),
                        "provenance": provenance(
                            DERIVED_FROM_REAL_DATA,
                            source=latest.get("image_id"),
                            method="SCL-masked Sentinel-2 NDWI candidate boundary and ee.Image.pixelArea()",
                            limitations=["Observed open-water extent; not permanent lake area, volume, or GLOF probability"],
                        ),
                    }
    evidence_lifecycle = build_evidence_lifecycle(
        observations=observations,
        temporal_evidence=temporal,
        multi_signal_identity=multi_signal_identity,
        authoritative_validation=authoritative_validation,
        derived_candidate_measurements=[
            measurement for measurement in derived_candidate_measurements
            if measurement.get("status") == "DERIVED_CANDIDATE_OPEN_WATER"
        ],
        authoritative_measurement=observed_measurement,
    )
    temporal_decision_support = {
        "status": INSUFFICIENT_DATA,
        "risk_available": False,
        "reason": "Temporal candidate evidence is not a complete multi-signal risk assessment",
        "provenance": provenance(
            UNAVAILABLE,
            source="Temporal evidence workflow",
            method="Risk and early-warning gates require a complete integrated observation",
        ),
    }
    temporal_early_warning = {
        "status": INSUFFICIENT_DATA,
        "reasons": [
            "Temporal workflow does not independently establish named-lake identity or complete risk evidence"
        ],
    }
    temporal_result = {
        "status": "SUCCESS",
        "region": region_key,
        "region_name": region["name"],
        "requested_date_range": {"start": start_date, "end": end_date},
        "geometry": {
            **geometry_metadata,
            "search_area": search_geometry,
            "analysis_area": discovery_geometry,
            "analysis_geometry_role": (
                "TRUSTED_REFERENCE_CONTEXT"
                if discovery_geometry is lake_geometry
                else "POLYGON_OPTIONAL_DISCOVERY_SEARCH"
            ),
        },
        "observations": observations,
        "acquisition_diagnostics": acquisition_diagnostics,
        "temporal_evidence": temporal,
        "multi_signal_identity": multi_signal_identity,
        "independent_satellite_data": independent_satellite_data,
        "lake_likeness": assess_lake_likeness(
            latest_candidates,
            temporal,
        ),
        "authoritative_boundary_validation": authoritative_validation,
        "evidence_lifecycle": evidence_lifecycle,
        "decision_support": temporal_decision_support,
        "early_warning_status": temporal_early_warning,
        "derived_candidate_measurements": derived_candidate_measurements,
        "observed_measurement": observed_measurement,
        "provenance": provenance(
            DERIVED_FROM_REAL_DATA,
            source=pipeline.COLLECTION,
            method="Multiple real Sentinel-2 observations with SCL masking and spatial candidate tracking",
            limitations=["Temporal persistence does not prove named-lake identity without independent validation"],
        ),
    }
    temporal_result["data_confidence"] = _data_confidence_summary(temporal_result)
    temporal_result["human_warning"] = build_human_warning(
        temporal_result, temporal_early_warning
    )
    return temporal_result


def _run_tsho_rolpa_temporal_evidence(start_date, end_date, max_observations=6):
    """Backward-compatible private Tsho Rolpa temporal runner."""
    return _run_temporal_evidence(
        "Tsho_Rolpa_Nepal", start_date, end_date, max_observations
    )


def run_temporal_evidence(region_key, start_date, end_date, max_observations=6):
    """Run multi-date evidence analysis and persist the complete run."""
    try:
        result = _run_temporal_evidence(region_key, start_date, end_date, max_observations)
    except Exception as exc:
        reliability = GEEReliabilityLayer()
        failure = reliability.failure("TEMPORAL_GEE_PROCESSING", exc)
        result = {
            "status": "UNAVAILABLE",
            "validity_status": "UNAVAILABLE",
            "region": region_key,
            "reason": failure["reason"],
            "reliability": {
                key: value for key, value in failure.items() if key != "value"
            },
            "observations": [],
            "temporal_evidence": {
                "identity_status": "UNAVAILABLE",
                "status": "UNAVAILABLE",
            },
            "provenance": provenance(
                UNAVAILABLE,
                source="Google Earth Engine",
                method="Temporal reliability-layer failure handling",
                limitations=["No usable multi-date satellite evidence was produced"],
            ),
        }
    result["data_confidence"] = _data_confidence_summary(result)
    result["human_warning"] = build_human_warning(result)
    try:
        record = ObservationStore().save_temporal_evidence(result)
        result["persistence"] = {
            "status": "SAVED",
            "run_id": record["run_id"],
            "recorded_at": record["recorded_at"],
        }
    except Exception as exc:
        result["persistence"] = {
            "status": "ERROR",
            "reason": f"Temporal evidence could not be persisted: {exc}",
        }
    return result


def run_tsho_rolpa_temporal_evidence(start_date, end_date, max_observations=6):
    """Backward-compatible Tsho Rolpa temporal evidence wrapper."""
    try:
        result = _run_tsho_rolpa_temporal_evidence(
            start_date, end_date, max_observations
        )
    except Exception as exc:
        reliability = GEEReliabilityLayer()
        failure = reliability.failure("TEMPORAL_GEE_PROCESSING", exc)
        result = {
            "status": "UNAVAILABLE",
            "validity_status": "UNAVAILABLE",
            "region": "Tsho_Rolpa_Nepal",
            "reason": failure["reason"],
            "reliability": {
                key: value for key, value in failure.items() if key != "value"
            },
            "observations": [],
            "temporal_evidence": {
                "identity_status": "UNAVAILABLE",
                "status": "UNAVAILABLE",
            },
            "provenance": provenance(
                UNAVAILABLE,
                source="Google Earth Engine",
                method="Temporal reliability-layer failure handling",
                limitations=["No usable multi-date satellite evidence was produced"],
            ),
        }
    result["data_confidence"] = _data_confidence_summary(result)
    result["human_warning"] = build_human_warning(result)
    try:
        record = ObservationStore().save_temporal_evidence(result)
        result["persistence"] = {
            "status": "SAVED",
            "run_id": record["run_id"],
            "recorded_at": record["recorded_at"],
        }
    except Exception as exc:
        result["persistence"] = {
            "status": "ERROR",
            "reason": f"Temporal evidence could not be persisted: {exc}",
        }
    return result


NEPAL_DEMO_REGION = "Tsho_Rolpa_Nepal"
NEPAL_SIMULATION_MODE = "nepal_simulation"


def _nepal_previous_simulated_area(scenario):
    """Previous scripted lake area from the scenario sequence (not GEE)."""
    consumed = scenario.current_event_index
    if consumed < 2:
        return None
    previous_event = scenario.event_sequence[consumed - 2]
    return scenario._estimate_lake_area(previous_event)


def nepal_telemetry_to_integrated_result(scenario, telemetry, region_key=NEPAL_DEMO_REGION):
    """Map Nepal telemetry onto the Phase 1 JSON envelope. Does not call GEE."""
    result = _integrated_result_skeleton(
        region_key,
        status="SUCCESS",
        mode=NEPAL_SIMULATION_MODE,
    )
    result["source"] = "nepal_simulation"
    result["collection"] = None
    result["simulated"] = True
    result["scenario"] = telemetry.get("scenario")
    result["simulation_phase"] = telemetry["phase"]
    result["simulation_event"] = telemetry.get("event_description")
    result["note"] = (
        "Scripted Nepal demonstration. Simulation phase is not the Risk Engine level. "
        "All satellite, sensor, and AI values in this mode are SIMULATED."
    )

    lake_area = telemetry["satellite_observation"]["lake_area_sqkm"]
    ndwi_value = telemetry["satellite_observation"]["ndwi_value"]
    previous_area = _nepal_previous_simulated_area(scenario)
    percent_change = None
    if previous_area not in (None, 0) and lake_area is not None:
        percent_change = ((lake_area - previous_area) / previous_area) * 100

    result["satellite"] = {
        "status": "simulated",
        "simulated": True,
        "note": "Scripted simulation values — NOT a live Sentinel-2 / GEE observation",
        "provenance": provenance(
            SCIENTIFIC_SIMULATION,
            source="NepalDisasterScenario",
            method="Hardcoded phase-based synthetic values",
            limitations=["Not a historical observation, forecast, or calibrated physical model"],
        ),
        "ndwi_value": ndwi_value,
        "water_area": {"area_sqkm": lake_area},
    }
    result["satellite_change"] = {
        "region": region_key,
        "status": "simulated" if previous_area is not None else "NOT_AVAILABLE",
        "simulated": True,
        "current_area_sqkm": lake_area,
        "previous_area_sqkm": previous_area,
        "percent_change": percent_change,
        "note": "Compared to the previous scripted scenario step, not a GEE baseline",
    }
    result["sensors"] = {
        "status": "simulated",
        "simulated": True,
        "source": "nepal_simulation",
        "note": "Simulated sensor data - NOT real measurements",
        "provenance": provenance(
            SIMULATED_SENSOR_DATA,
            source="NepalDisasterScenario",
            method="Hardcoded phase-based synthetic values",
        ),
        "vibration_cmps": telemetry["sensors"]["vibration_cmps"],
        "water_level_cm": telemetry["sensors"]["water_level_cm"],
    }
    result["ai"] = {
        "status": "SIMULATED_SUPPORTING_SIGNAL",
        "simulated": True,
        "detector_type": "nepal_scripted_anomaly",
        "signal": telemetry["ai_detection"]["anomaly_score"],
        "note": (
            "Not YOLOv8 and not a GLOF-trained detector. "
            "Scripted supporting signal for the Nepal demonstration only."
        ),
        "provenance": provenance(
            SCIENTIFIC_SIMULATION,
            source="NepalDisasterScenario",
            method="Hardcoded phase-based supporting signal",
            limitations=["Not a YOLO result and not a validated GLOF detector"],
        ),
    }
    assessment = telemetry["engine_assessment"]
    risk = dict(assessment)
    risk.update({
        "region": region_key,
        "source": "prototype_demo_logic",
        "simulation_phase": telemetry["phase"],
    })
    result["risk"] = risk
    result["history"] = list(scenario.risk_engine.history)
    result["data_confidence"] = _data_confidence_summary(result)
    result["human_warning"] = build_human_warning(
        result,
        {
            "status": "UNCONFIRMED",
            "reasons": ["This is a scripted simulation, not a verified warning observation."],
            "evidence_state": {"risk_assessment_status": risk.get("assessment_status")},
        },
    )
    return result


def run_nepal_simulation_step(scenario=None, region_key=NEPAL_DEMO_REGION):
    """
    Advance the Nepal scenario by one phase and return a Phase 1 JSON envelope.

    Does not use Google Earth Engine. Reuse the same scenario instance so
    RiskEngine history accumulates across steps.
    Returns None when the five-phase sequence is finished.
    """
    if scenario is None:
        scenario = NepalDisasterScenario()
    telemetry = scenario.generate_telemetry()
    if telemetry is None:
        return None
    return nepal_telemetry_to_integrated_result(scenario, telemetry, region_key)


def run_nepal_simulation_sequence(region_key=NEPAL_DEMO_REGION):
    """Run all five Nepal phases on one RiskEngine instance (no GEE)."""
    scenario = NepalDisasterScenario()
    steps = []
    while True:
        result = run_nepal_simulation_step(scenario, region_key=region_key)
        if result is None:
            break
        steps.append(result)
    return steps


def demo_sensor_network():
    """Demo: Virtual sensor network in Nepal."""
    
    print("\n" + "="*60)
    print("DEMO 1: Virtual Sensor Network (Nepal - Pokhara)")
    print("="*60)
    
    # Create sensor network
    network = SensorNetwork("Nepal_Pokhara")
    
    # Add sensors
    network.add_vibration_sensor("VIB-001")
    network.add_water_level_sensor("WATER-001", normal_level=150)
    
    # Read sensors (normal conditions)
    print("\n→ Reading sensors (normal conditions)...")
    readings = network.read_all_sensors()
    print(json.dumps(readings, indent=2))
    
    # Read sensors with anomaly
    print("\n→ Reading sensors (with anomaly)...")
    readings_anomaly = network.read_all_sensors(
        anomaly_factors={"VIB-001": 0.5, "WATER-001": 0.3}
    )
    print(json.dumps(readings_anomaly, indent=2))
    
    return network


def demo_nepal_disaster():
    """Demo: Nepal disaster simulation sequence (Risk Engine is the risk source)."""
    
    print("\n" + "="*60)
    print("DEMO 2: Nepal Disaster Simulation (Aug 26, 2026) — SIMULATED")
    print("="*60)
    print("Simulation PHASE is the scripted story. risk.risk_level is the engine assessment.")
    
    steps = run_nepal_simulation_sequence()
    print(f"\n→ {len(steps)} phases. Shared history length={len(steps[-1]['history']) if steps else 0}")
    
    for event_index, result in enumerate(steps, start=1):
        risk = result["risk"]
        print(f"\n--- EVENT {event_index} ---")
        print(f"Simulation phase: {result['simulation_phase']}")
        print(f"Risk Engine level: {risk['risk_level']} (score={risk['risk_score']})")
        print(f"Action: {risk['action']}")
        print(f"Vibration: {result['sensors']['vibration_cmps']} cm/s² (simulated)")
        print(f"Water Level: {result['sensors']['water_level_cm']} cm (simulated)")
    
    return steps


def demo_risk_engine():
    """Demo: Risk engine assessment."""
    
    print("\n" + "="*60)
    print("DEMO 3: Risk Engine Assessment")
    print("="*60)
    
    engine = RiskEngine()
    
    # Scenario 1: All normal
    print("\n→ Assessment 1: Normal conditions")
    assessment = engine.assess_risk(
        satellite_signal=0.1,
        ai_signal=0.05,
        sensor_signal=0.15
    )
    print(json.dumps(assessment, indent=2))
    
    # Scenario 2: Satellite signal high
    print("\n→ Assessment 2: High satellite signal (water increase)")
    assessment = engine.assess_risk(
        satellite_signal=0.7,
        ai_signal=0.2,
        sensor_signal=0.3
    )
    print(json.dumps(assessment, indent=2))
    
    # Scenario 3: Multiple high signals
    print("\n→ Assessment 3: Multiple high signals (CRITICAL)")
    assessment = engine.assess_risk(
        satellite_signal=0.8,
        ai_signal=0.7,
        sensor_signal=0.75
    )
    print(json.dumps(assessment, indent=2))
    
    return engine


def demo_regions():
    """Demo: Available monitoring regions."""
    
    print("\n" + "="*60)
    print("DEMO 4: Available Monitoring Regions")
    print("="*60)
    
    regions = HIMALAYAN_REGIONS
    
    print("\nAvailable regions:")
    for key, region in regions.items():
        print(f"\n  • {region['name']}")
        print(f"    Lake: {region['lake_name']}")
        print(f"    Country: {region['country']}")
        print(f"    Coords: ({region['latitude']}, {region['longitude']})")


def demo_integrated_monitoring(region_keys=None):
    """Demo: fresh satellite requests for configured Himalayan regions."""
    print("\n" + "=" * 60)
    print("DEMO 5: Dynamic Pan-Himalayan Satellite Monitoring")
    print("=" * 60)

    region_keys = region_keys or HIMALAYAN_REGIONS.keys()
    for region_key in region_keys:
        print(f"\n→ Fresh GEE request for {region_key}...")
        observation = run_integrated_monitoring(region_key)
        print(json.dumps(observation, indent=2))


def main():
    """Run all demos."""
    
    print("\n" + "="*70)
    print("  G-ALERT BACKEND - Himalayan Glacial Lake Early Warning System")
    print("  Hackathon Prototype (SIMULATED DATA)")
    print("="*70)
    
    # Demo 1: Regions
    demo_regions()
    
    # Demo 2: Sensor network
    demo_sensor_network()
    
    # Demo 3: Nepal disaster
    demo_nepal_disaster()
    
    # Demo 4: Risk engine
    demo_risk_engine()

    # Demo 5: Dynamic satellite integration for two regions
    demo_integrated_monitoring()
    
    print("\n" + "="*70)
    print("  Demos complete!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
