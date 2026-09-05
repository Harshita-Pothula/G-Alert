"""Shared provenance labels for G-ALERT observations and decisions."""

REAL_SATELLITE_DATA = "REAL_SATELLITE_DATA"
REAL_SENSOR_DATA = "REAL_SENSOR_DATA"
DERIVED_FROM_REAL_DATA = "DERIVED_FROM_REAL_DATA"
SIMULATED_SENSOR_DATA = "SIMULATED_SENSOR_DATA"
SCIENTIFIC_SIMULATION = "SCIENTIFIC_SIMULATION"
PROTOTYPE_ASSUMPTION = "PROTOTYPE_ASSUMPTION"
UNKNOWN = "UNKNOWN"
UNAVAILABLE = "UNAVAILABLE"

VALID_PROVENANCE = {
    REAL_SATELLITE_DATA,
    REAL_SENSOR_DATA,
    DERIVED_FROM_REAL_DATA,
    SIMULATED_SENSOR_DATA,
    SCIENTIFIC_SIMULATION,
    PROTOTYPE_ASSUMPTION,
    UNKNOWN,
    UNAVAILABLE,
}


def provenance(provenance_type, *, source=None, method=None, limitations=None):
    """Return a small, JSON-safe provenance record."""
    if provenance_type not in VALID_PROVENANCE:
        raise ValueError(f"Unsupported provenance type: {provenance_type}")
    return {
        "type": provenance_type,
        "source": source,
        "method": method,
        "limitations": list(limitations or []),
    }
