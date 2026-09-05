"""Historical seasonal reference calculations for satellite observations."""

from datetime import date, datetime
from math import sqrt
from statistics import mean, median


BASELINE_VALID = "VALID"
BASELINE_INSUFFICIENT = "INSUFFICIENT_HISTORICAL_DATA"


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    return None


def calendar_period(value, period="month"):
    """Return a calendar grouping key for a date or ISO timestamp."""
    observation_date = _as_date(value)
    if observation_date is None:
        return None
    if period == "month":
        return f"{observation_date.month:02d}"
    if period == "season":
        return ((observation_date.month % 12) // 3) + 1
    raise ValueError("period must be 'month' or 'season'")


def _valid_value(observation, value_key):
    value = observation.get(value_key)
    if not isinstance(value, (int, float)):
        return None
    if observation.get("status") not in {None, "SUCCESS", "VALID"}:
        return None
    return float(value)


def calculate_seasonal_baseline(
    historical_observations,
    current_date,
    *,
    value_key="water_area_sqkm",
    period="month",
    minimum_observations=3,
):
    """Calculate a reference distribution from multiple matching observations.

    Historical records are expected to contain a date-like ``acquisition_time``
    or ``date`` field and the selected numeric value. Records are returned in
    the result so provenance, quality, and identity context remain traceable.
    """
    current_period = calendar_period(current_date, period)
    if current_period is None:
        raise ValueError("current_date must be date-like")
    if not isinstance(minimum_observations, int) or minimum_observations < 1:
        raise ValueError("minimum_observations must be a positive integer")

    matching = []
    excluded = []
    for observation in historical_observations or []:
        observation_date = observation.get("acquisition_time") or observation.get("date")
        if calendar_period(observation_date, period) != current_period:
            excluded.append({"observation": observation, "reason": "DIFFERENT_PERIOD"})
            continue
        value = _valid_value(observation, value_key)
        if value is None:
            excluded.append({"observation": observation, "reason": "INVALID_VALUE_OR_STATUS"})
            continue
        matching.append({"observation": observation, "value": value})

    values = [item["value"] for item in matching]
    result = {
        "status": BASELINE_VALID if len(values) >= minimum_observations else BASELINE_INSUFFICIENT,
        "period": period,
        "period_key": current_period,
        "value_key": value_key,
        "minimum_observations": minimum_observations,
        "observation_count": len(values),
        "observations": [item["observation"] for item in matching],
        "excluded_observations": excluded,
        "statistics": None,
        "provenance": {
            "type": "DERIVED_FROM_REAL_DATA",
            "method": "Multi-date same-calendar-period historical reference",
            "limitations": [
                "Historical reference is not a forecast or risk threshold",
                "Seasonal representativeness depends on the available acquisition record",
            ],
        },
    }
    if len(values) < minimum_observations:
        result["reason"] = (
            f"Only {len(values)} valid historical observations match period "
            f"{current_period}; {minimum_observations} are required"
        )
        return result

    average = mean(values)
    variance = mean((value - average) ** 2 for value in values)
    result["statistics"] = {
        "count": len(values),
        "mean": average,
        "median": median(values),
        "minimum": min(values),
        "maximum": max(values),
        "range": {"minimum": min(values), "maximum": max(values)},
        "standard_deviation": sqrt(variance),
    }
    return result


def evaluate_against_seasonal_baseline(
    current_observation,
    historical_observations,
    *,
    value_key="water_area_sqkm",
    period="month",
    minimum_observations=3,
):
    """Compare one current value with its multi-date seasonal reference."""
    if not isinstance(current_observation, dict):
        raise ValueError("current_observation must be a dictionary")
    current_value = current_observation.get(value_key)
    baseline = calculate_seasonal_baseline(
        historical_observations,
        current_observation.get("acquisition_time") or current_observation.get("date"),
        value_key=value_key,
        period=period,
        minimum_observations=minimum_observations,
    )
    comparison = {
        "status": "NOT_AVAILABLE",
        "current_value": current_value,
        "baseline_status": baseline["status"],
        "baseline": baseline,
        "deviation": None,
        "deviation_percentage": None,
        "provenance": baseline["provenance"],
    }
    if baseline["status"] != BASELINE_VALID:
        comparison["reason"] = baseline["reason"]
        return comparison
    if not isinstance(current_value, (int, float)):
        comparison["reason"] = "Current observation does not contain a valid comparison value"
        return comparison

    baseline_value = baseline["statistics"]["mean"]
    deviation = current_value - baseline_value
    comparison["status"] = "VALID"
    comparison["baseline_value"] = baseline_value
    comparison["deviation"] = deviation
    if baseline_value != 0:
        comparison["deviation_percentage"] = (deviation / baseline_value) * 100
    else:
        comparison["reason"] = "Baseline mean is zero; deviation percentage is unavailable"
    return comparison