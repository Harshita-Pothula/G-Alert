"""Approximate downstream impact-corridor screening."""

import math
import os


SCREENING_STATUS = "SCREENING_APPROXIMATE"
UNAVAILABLE_STATUS = "UNAVAILABLE"


def _distance_km(latitude_a, longitude_a, latitude_b, longitude_b):
    if not all(isinstance(value, (int, float)) for value in (latitude_a, longitude_a, latitude_b, longitude_b)):
        return None
    radius = 6371.0
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = math.radians(latitude_b - latitude_a)
    delta_lon = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _feature_distance(feature, lake):
    return _distance_km(
        lake["latitude"],
        lake["longitude"],
        feature.get("latitude"),
        feature.get("longitude"),
    )


def _near_waterway(feature, waterways, corridor_width_km):
    distances = [
        _distance_km(
            feature.get("latitude"),
            feature.get("longitude"),
            waterway.get("latitude"),
            waterway.get("longitude"),
        )
        for waterway in waterways
    ]
    distances = [distance for distance in distances if isinstance(distance, (int, float))]
    return min(distances) if distances else None


def build_impact_mapping(region_key, region, automated_context=None):
    """Build a conservative corridor screen from available point/way evidence."""
    region = region or {}
    context = automated_context or {}
    if context.get("region_key") not in (None, region_key):
        raise ValueError("automated impact context does not match requested region")
    lake = {
        "latitude": region.get("latitude"),
        "longitude": region.get("longitude"),
        "name": region.get("lake_name") or region.get("name"),
    }
    waterways = context.get("river_or_drainage_path") or []
    settlements = context.get("settlements") or []
    infrastructure = context.get("vulnerable_infrastructure") or []
    radius_by_hazard = {"CRITICAL": 50.0, "HIGH": 35.0, "MODERATE": 25.0}
    radius_km = float(os.getenv(
        "G_ALERT_IMPACT_SCREENING_RADIUS_KM",
        radius_by_hazard.get(region.get("hazard_level"), 25.0),
    ))
    corridor_width_km = float(os.getenv("G_ALERT_IMPACT_CORRIDOR_WIDTH_KM", "5"))

    limitations = [
        "SCREENING_APPROXIMATE: this is not a hydrodynamic flood simulation",
        "No exact flood depth, arrival time, inundation boundary, or guaranteed impact is calculated",
        "Flow direction and lake-outlet connectivity are not verified by this screening method",
        "Missing settlements or infrastructure do not imply no downstream impact",
    ]
    if not waterways:
        return {
            "region": region_key,
            "status": UNAVAILABLE_STATUS,
            "classification": SCREENING_STATUS,
            "corridor": None,
            "exposed_settlements": [],
            "exposed_infrastructure": [],
            "population": {"value": None, "status": "UNAVAILABLE"},
            "source": context.get("sources", []),
            "methodology": "No automated waterway features were available for corridor screening",
            "confidence": "LOW",
            "limitations": limitations + ["No waterway geometry was available; an impact corridor was not inferred"],
        }

    waterway_points = [
        waterway for waterway in waterways
        if isinstance(waterway.get("latitude"), (int, float))
        and isinstance(waterway.get("longitude"), (int, float))
        and _feature_distance(waterway, lake) <= radius_km
    ]
    if not waterway_points:
        return {
            "region": region_key,
            "status": UNAVAILABLE_STATUS,
            "classification": SCREENING_STATUS,
            "corridor": None,
            "exposed_settlements": [],
            "exposed_infrastructure": [],
            "population": {"value": None, "status": "UNAVAILABLE"},
            "source": context.get("sources", []),
            "methodology": "Discovered waterways did not fall within the configured screening radius",
            "confidence": "LOW",
            "limitations": limitations + ["No connected downstream waterway could be established from available point evidence"],
        }

    def exposed(feature):
        lake_distance = _feature_distance(feature, lake)
        waterway_distance = _near_waterway(feature, waterway_points, corridor_width_km)
        return (
            isinstance(lake_distance, (int, float))
            and lake_distance <= radius_km
            and isinstance(waterway_distance, (int, float))
            and waterway_distance <= corridor_width_km
        )

    exposed_settlements = [
        {**settlement, "distance_to_lake_km": _feature_distance(settlement, lake), "status": "COMMUNITY_DATA"}
        for settlement in settlements if exposed(settlement)
    ]
    exposed_infrastructure = [
        {**asset, "distance_to_lake_km": _feature_distance(asset, lake), "status": "COMMUNITY_DATA"}
        for asset in infrastructure if exposed(asset)
    ]
    populations = [
        item.get("population") for item in exposed_settlements
        if isinstance(item.get("population"), (int, float))
    ]
    population = {
        "value": sum(populations) if populations else None,
        "status": "COMMUNITY_DATA" if populations else "UNAVAILABLE",
        "source": "OpenStreetMap",
        "limitations": ["Only explicit OSM population tags are counted; this is not a census"],
    }
    return {
        "region": region_key,
        "status": SCREENING_STATUS,
        "classification": SCREENING_STATUS,
        "corridor": {
            "type": "APPROXIMATE_WATERWAY_SCREENING_CORRIDOR",
            "origin": lake,
            "waterway_features": waterway_points,
            "radius_km": radius_km,
            "width_km": corridor_width_km,
            "directionality": "UNVERIFIED",
        },
        "exposed_settlements": exposed_settlements,
        "exposed_infrastructure": exposed_infrastructure,
        "population": population,
        "source": context.get("sources", []),
        "methodology": "Candidates are within the lake-centered screening radius and near discovered waterway features",
        "confidence": "LOW" if not exposed_settlements and not exposed_infrastructure else "MEDIUM",
        "limitations": limitations,
    }
