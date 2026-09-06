"""Centralized region identity validation for G-ALERT data boundaries."""

from satellite.region_config import HIMALAYAN_REGIONS


class RegionIntegrityError(ValueError):
    """Raised when data cannot be proven to belong to the requested region."""


def require_valid_region(region_key):
    if not isinstance(region_key, str) or region_key not in HIMALAYAN_REGIONS:
        raise RegionIntegrityError(f"Unknown or invalid region: {region_key!r}")
    return region_key


def require_region_match(expected_region, actual_region, field="region"):
    require_valid_region(expected_region)
    if actual_region != expected_region:
        raise RegionIntegrityError(
            f"{field} does not match requested region: expected {expected_region!r}, got {actual_region!r}"
        )
    return actual_region


def validate_observation(observation, expected_region=None):
    if not isinstance(observation, dict):
        raise RegionIntegrityError("observation must be a dictionary")
    actual_region = observation.get("region")
    require_valid_region(actual_region)
    if expected_region is not None:
        require_region_match(expected_region, actual_region, "observation.region")
    satellite = observation.get("satellite") or {}
    satellite_region = satellite.get("region")
    if satellite_region is not None:
        require_region_match(actual_region, satellite_region, "satellite.region")
    return actual_region


def validate_region_context(region_key, context):
    require_valid_region(region_key)
    if not isinstance(context, dict):
        raise RegionIntegrityError("region context must be a dictionary")
    context_region = context.get("region_key")
    if context_region is not None:
        require_region_match(region_key, context_region, "context.region_key")
    return context
