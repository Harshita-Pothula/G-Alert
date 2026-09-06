"""Scalable automated downstream exposure discovery using global public data."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests


OVERPASS_DEFAULT_URL = "https://overpass-api.de/api/interpreter"
CACHE_SCHEMA = "downstream-exposure-v1"


def _bbox_from_geometry(geometry, latitude, longitude, radius_degrees=0.35):
    coordinates = []
    if isinstance(geometry, dict):
        coordinates = geometry.get("coordinates") or []

    def collect(value):
        if isinstance(value, (list, tuple)) and len(value) == 2 and all(
            isinstance(item, (int, float)) for item in value
        ):
            return [value]
        result = []
        for item in value if isinstance(value, (list, tuple)) else []:
            result.extend(collect(item))
        return result

    points = collect(coordinates)
    if not points:
        return (
            latitude - radius_degrees,
            longitude - radius_degrees,
            latitude + radius_degrees,
            longitude + radius_degrees,
        )
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return min(latitudes), min(longitudes), max(latitudes), max(longitudes)


def _cache_path():
    return Path(os.getenv("G_ALERT_DOWNSTREAM_CACHE_DB", "gee_cache/downstream_exposure.sqlite3"))


def _initialize_cache(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS downstream_cache (cache_key TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload_json TEXT NOT NULL)"
    )
    connection.commit()
    return connection


def _cache_key(region_key, bbox):
    return f"{CACHE_SCHEMA}:{region_key}:{','.join(f'{value:.5f}' for value in bbox)}"


def _read_cache(region_key, bbox, max_age_hours):
    path = _cache_path()
    connection = _initialize_cache(path)
    try:
        row = connection.execute(
            "SELECT created_at, payload_json FROM downstream_cache WHERE cache_key = ?",
            (_cache_key(region_key, bbox),),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    try:
        created_at = datetime.fromisoformat(row[0])
        age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
        if age_hours > max_age_hours:
            return None
        payload = json.loads(row[1])
        if payload.get("region_key") != region_key:
            return None
        payload["cache"] = {"status": "HIT", "age_hours": round(age_hours, 2)}
        return payload
    except (ValueError, json.JSONDecodeError):
        return None


def _write_cache(region_key, bbox, payload):
    path = _cache_path()
    connection = _initialize_cache(path)
    try:
        connection.execute(
            "INSERT OR REPLACE INTO downstream_cache (cache_key, created_at, payload_json) VALUES (?, ?, ?)",
            (
                _cache_key(region_key, bbox),
                datetime.now(timezone.utc).isoformat(),
                json.dumps(payload, sort_keys=True, allow_nan=False),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _overpass_query(bbox):
    south, west, north, east = bbox
    area = f"({south},{west},{north},{east})"
    return f"""[out:json][timeout:20];(
  way[waterway]({area});
  nwr[place]({area});
  way[highway]({area});
  way[bridge]({area});
  nwr[amenity~\"school|hospital\"]({area});
  nwr[power]({area});
  nwr[man_made=dam]({area});
);out center tags;"""


def _value(tags, key):
    value = tags.get(key)
    return value if value not in (None, "") else None


def _parse_population(value):
    if not isinstance(value, str):
        return None
    try:
        return int(float(value.replace(",", "")))
    except ValueError:
        return None


def _normalize_elements(elements):
    rivers = []
    settlements = []
    infrastructure = []
    population_total = 0
    population_records = 0
    for element in elements:
        tags = element.get("tags") or {}
        item = {
            "osm_id": f"{element.get('type')}:{element.get('id')}",
            "name": _value(tags, "name"),
            "latitude": (element.get("center") or {}).get("lat") or element.get("lat"),
            "longitude": (element.get("center") or {}).get("lon") or element.get("lon"),
            "tags": tags,
            "source": "OpenStreetMap",
            "status": "COMMUNITY_DATA",
        }
        if tags.get("waterway"):
            rivers.append(item)
            continue
        if tags.get("place"):
            population = _parse_population(tags.get("population"))
            if population is not None:
                population_total += population
                population_records += 1
            item["population"] = population
            settlements.append(item)
            continue
        asset_type = None
        if tags.get("bridge"):
            asset_type = "bridge"
        elif tags.get("highway"):
            asset_type = "road"
        elif tags.get("amenity") in {"school", "hospital"}:
            asset_type = tags["amenity"]
        elif tags.get("power"):
            asset_type = f"power_{tags['power']}"
        elif tags.get("man_made") == "dam":
            asset_type = "dam"
        if asset_type:
            item["asset_type"] = asset_type
            infrastructure.append(item)

    return {
        "river_or_drainage_path": rivers,
        "settlements": settlements,
        "population": {
            "value": population_total if population_records else None,
            "status": "COMMUNITY_DATA" if population_records else "UNAVAILABLE",
            "counted_settlements": population_records,
            "source": "OpenStreetMap",
            "limitations": [
                "OSM population tags are incomplete and not a census",
                "No population value was inferred for settlements without an explicit population tag",
            ],
        },
        "vulnerable_infrastructure": infrastructure,
    }


def fetch_automated_downstream_context(
    region_key,
    latitude,
    longitude,
    geometry=None,
    *,
    timeout=5,
    cache_hours=24,
):
    """Return cached or live global baseline context without raising errors."""
    bbox = _bbox_from_geometry(geometry, latitude, longitude)
    cached = _read_cache(region_key, bbox, cache_hours)
    if cached is not None:
        return cached

    result = {
        "region_key": region_key,
        "status": "UNAVAILABLE",
        "provider": "GLOBAL_BASELINE",
        "bbox": bbox,
        "sources": [],
        "river_or_drainage_path": [],
        "settlements": [],
        "population": {
            "value": None,
            "status": "UNAVAILABLE",
            "source": None,
            "limitations": ["No population dataset was available from the automated baseline provider"],
        },
        "vulnerable_infrastructure": [],
        "limitations": [
            "Automated baseline discovery is a screening result, not authoritative local mapping",
            "No downstream exposure is inferred from missing features",
        ],
    }
    try:
        query = _overpass_query(bbox)
        endpoint = os.getenv("G_ALERT_OVERPASS_URL", OVERPASS_DEFAULT_URL)
        response = requests.post(
            endpoint,
            data=query,
            headers={"User-Agent": "G-ALERT downstream exposure baseline"},
            timeout=timeout,
        )
        response.raise_for_status()
        normalized = _normalize_elements((response.json() or {}).get("elements") or [])
        result.update(normalized)
        result["status"] = "COMMUNITY_DATA"
        result["sources"] = [{
            "name": "OpenStreetMap",
            "type": "COMMUNITY_DATA",
            "endpoint": endpoint,
            "method": "Overpass geographic query",
            "bbox": bbox,
        }]
        result["cache"] = {"status": "MISS"}
        _write_cache(region_key, bbox, result)
        return result
    except Exception as exc:
        result["reason"] = str(exc)
        result["cache"] = {"status": "MISS"}
        return result
