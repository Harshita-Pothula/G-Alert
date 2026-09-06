"""Real external weather evidence for G-ALERT monitoring regions."""

from datetime import datetime, timezone


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_SOURCE = "Open-Meteo"


def _parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def rainfall_signal(rainfall_mmph):
    """Map real rainfall intensity to the existing bounded environmental signal."""
    if not isinstance(rainfall_mmph, (int, float)) or rainfall_mmph < 0:
        return None
    if rainfall_mmph >= 50:
        return 1.0
    if rainfall_mmph >= 25:
        return 0.6
    if rainfall_mmph >= 10:
        return 0.3
    return 0.0


def fetch_weather_observation(latitude, longitude, *, timeout=10, max_age_hours=6):
    """Fetch current and recent rainfall from Open-Meteo without raising to callers."""
    result = {
        "status": "UNAVAILABLE",
        "source": WEATHER_SOURCE,
        "source_url": OPEN_METEO_URL,
        "observation_time": None,
        "latitude": latitude,
        "longitude": longitude,
        "rainfall_mmph": None,
        "rainfall_24h_mm": None,
        "signal": None,
        "provenance": {
            "type": "UNAVAILABLE",
            "source": WEATHER_SOURCE,
            "method": "Open-Meteo current and hourly rainfall query",
            "limitations": [],
        },
    }
    try:
        import requests

        response = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "rain,precipitation",
                "hourly": "rain,precipitation",
                "past_days": 1,
                "forecast_days": 1,
                "timezone": "UTC",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        current = payload.get("current") or {}
        observation_time = current.get("time")
        observed_at = _parse_timestamp(observation_time)
        now = datetime.now(timezone.utc)
        if observed_at is None:
            result["provenance"]["limitations"].append("Weather observation time is missing or invalid")
            return result
        if abs((now - observed_at).total_seconds()) > max_age_hours * 3600:
            result.update({"status": "STALE", "observation_time": observation_time})
            result["provenance"]["limitations"].append("Weather observation is older than the freshness limit")
            return result

        rainfall = current.get("rain")
        if not isinstance(rainfall, (int, float)):
            rainfall = current.get("precipitation")
        if not isinstance(rainfall, (int, float)):
            result["observation_time"] = observation_time
            result["provenance"]["limitations"].append("Current rainfall value is missing")
            return result

        hourly = payload.get("hourly") or {}
        hourly_rain = hourly.get("rain") or []
        rainfall_24h = sum(value for value in hourly_rain[-24:] if isinstance(value, (int, float)))
        result.update({
            "status": "SUCCESS",
            "observation_time": observation_time,
            "rainfall_mmph": float(rainfall),
            "rainfall_24h_mm": round(rainfall_24h, 2),
            "signal": rainfall_signal(float(rainfall)),
            "provenance": {
                "type": "REAL_WEATHER_DATA",
                "source": WEATHER_SOURCE,
                "method": "Open-Meteo current and hourly rainfall query",
                "limitations": [
                    "Rainfall is point-based regional weather data, not a lake-gauge measurement",
                    "Rainfall signal thresholds are prototype decision-support thresholds",
                ],
            },
        })
        return result
    except Exception as exc:
        result["provenance"]["limitations"].append(f"Weather request failed: {exc}")
        result["reason"] = str(exc)
        return result
