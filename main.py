"""
main.py - Quick start and demo script for G-ALERT backend
"""

from satellite.region_config import HIMALAYAN_REGIONS, get_region_bounds, get_region_analysis_bounds, get_region_info
from satellite.gee_pipeline import initialize_gee_pipeline
from satellite.image_cache import get_image_cache
from simulation.sensor_simulator import SensorNetwork, SensorObservation
from simulation.nepal_disaster import NepalDisasterScenario
from risk_engine import RiskEngine, RiskAssessment
from ai.yolov8_detector import Detection, AIObservation, YOLOv8Detector
from satellite.ndwi_analysis import WaterObservation

import json
from datetime import datetime, timedelta, timezone


INTEGRATED_RESULT_KEYS = (
    "status",
    "region",
    "satellite",
    "satellite_change",
    "sensors",
    "ai",
    "risk",
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
        "processed_at": processed_at,
        "satellite": {"status": "NOT_AVAILABLE"},
        "satellite_change": {"status": "NOT_AVAILABLE"},
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
        "downstream_exposure": (region or {}).get("downstream_exposure"),
        "history": [],
    }
    if reason is not None:
        result["reason"] = reason
    return result


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


def run_integrated_monitoring(region_key, start_date=None, end_date=None, mode="monitoring"):
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

    start_date, end_date = _date_range(start_date, end_date)
    bounds = get_region_bounds(region_key)
    analysis_bounds = get_region_analysis_bounds(region_key)
    result = _integrated_result_skeleton(
        region_key,
        status="ERROR",
        mode=mode,
        processed_at=processed_at,
    )
    result["requested_date_range"] = {"start": start_date, "end": end_date}

    pipeline = initialize_gee_pipeline()
    if pipeline is None:
        result["reason"] = "Google Earth Engine authentication failed"
        return result

    # Use fallback-enabled image retrieval for robust live demos
    image, search_metadata = pipeline.get_sentinel2_image_with_fallback(
        bounds, start_date, end_date, cloud_cover_max=20
    )
    
    if image is None:
        result["status"] = "NO_SUITABLE_IMAGERY"
        result["reason"] = "No suitable Sentinel-2 imagery available even with expanded search"
        result["image_search_metadata"] = search_metadata
        return result
    
    # Add search metadata to result for transparency
    result["image_search_metadata"] = search_metadata

    import ee

    geometry = ee.Geometry(bounds)
    metadata = pipeline.last_metadata.get("properties", {})
    acquisition_ms = metadata.get("system:time_start")
    acquisition_time = datetime.fromtimestamp(acquisition_ms / 1000, timezone.utc).isoformat() if acquisition_ms else None
    rgb = image.select(["B4", "B3", "B2"]).visualize(
        min=0, max=3000, gamma=1.2, forceRgbOutput=True
    ).clip(geometry)
    image_url = rgb.getThumbURL({"region": bounds, "dimensions": 512, "format": "png"})

    from satellite.ndwi_analysis import NDWIAnalyzer
    ndwi_analyzer = NDWIAnalyzer()
    ndwi_image = ndwi_analyzer.calculate_ndwi(image)
    water_mask = ndwi_analyzer.create_water_mask(ndwi_image)
    water_area = ndwi_analyzer.calculate_water_area(water_mask, analysis_bounds)

    baseline = {"status": "NOT_AVAILABLE", "reason": "No earlier same-region Sentinel-2 image was found"}
    previous_area = None
    current_acquisition_ms = metadata.get("system:time_start")
    if current_acquisition_ms:
        minimum_baseline_time_ms = current_acquisition_ms - (5 * 24 * 60 * 60 * 1000)
        baseline_start = (
            datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=30)
        ).strftime("%Y-%m-%d")
        baseline_collection = (
            ee.ImageCollection(pipeline.COLLECTION)
            .filterBounds(geometry)
            .filterDate(baseline_start, end_date)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 50))
            .filter(ee.Filter.lt("system:time_start", minimum_baseline_time_ms))
            .sort("system:time_start", opt_ascending=False)
        )
        if baseline_collection.size().getInfo() > 0:
            baseline_image = baseline_collection.first()
            baseline_metadata = baseline_image.getInfo().get("properties", {})
            baseline_ndwi = ndwi_analyzer.calculate_ndwi(baseline_image)
            baseline_mask = ndwi_analyzer.create_water_mask(baseline_ndwi)
            baseline_area = ndwi_analyzer.calculate_water_area(baseline_mask, analysis_bounds)
            previous_area = (baseline_area or {}).get("area_sqkm")
            baseline_ms = baseline_metadata.get("system:time_start")
            baseline["status"] = "SUCCESS"
            baseline.update({
                "image_id": baseline_metadata.get("system:index"),
                "acquisition_time": datetime.fromtimestamp(baseline_ms / 1000, timezone.utc).isoformat() if baseline_ms else None,
                "cloud_cover_percent": baseline_metadata.get("CLOUDY_PIXEL_PERCENTAGE"),
                "water_area": baseline_area
            })
    current_area_sqkm = (water_area or {}).get("area_sqkm")
    baseline_area_sqkm = (baseline.get("water_area") or {}).get("area_sqkm")
    current_area_valid = isinstance(current_area_sqkm, (int, float))
    baseline_area_valid = isinstance(baseline_area_sqkm, (int, float))
    cloud_values = [
        value for value in (
            metadata.get("CLOUDY_PIXEL_PERCENTAGE"),
            baseline.get("cloud_cover_percent")
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
        "baseline_cloud_cover_percent": baseline.get("cloud_cover_percent"),
        "current_water_area_valid": current_area_valid,
        "baseline_water_area_valid": baseline_area_valid,
        "comparison_status": "VALID" if comparison_valid else "NOT_AVAILABLE"
    }
    analysis_geometry = ee.Geometry(analysis_bounds)
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
        "water_area": water_area,
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
    if previous_area is not None:
        satellite_signal_inputs["previous_area_sqkm"] = previous_area
    satellite_signal = engine.calculate_satellite_signal(satellite_signal_inputs)
    previous_area_sqkm = previous_area
    percent_change = None
    if previous_area_sqkm is not None and current_area_sqkm is not None and previous_area_sqkm != 0:
        percent_change = ((current_area_sqkm - previous_area_sqkm) / previous_area_sqkm) * 100
    result["satellite_change"] = {
        "current_area_sqkm": current_area_sqkm,
        "previous_area_sqkm": previous_area_sqkm,
        "percent_change": percent_change,
        "satellite_risk_signal": satellite_signal,
        "data_quality_confidence": data_quality["confidence"],
        "status": "CALCULATED" if previous_area_sqkm is not None else "NOT_AVAILABLE",
        "note": "Previous area is omitted from RiskEngine when no same-region baseline exists"
    }
    result["sensors"] = sensor_readings or {
        "status": "NOT_RUN",
        "note": "Virtual sensors run only in simulation mode",
        "simulated": True,
    }
    result["ai"] = ai_result
    _attach_risk_and_history(
        result,
        engine,
        satellite_signal,
        ai_signal,
        sensor_signal,
        region_key,
    )
    result["status"] = "SUCCESS"
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
        "ndwi_value": ndwi_value,
        "water_area": {"area_sqkm": lake_area},
    }
    result["satellite_change"] = {
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
