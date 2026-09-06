"""Reliability and explicit-unavailability contracts for active GEE work."""

from copy import deepcopy

from provenance import UNAVAILABLE, provenance


class GEEReliabilityLayer:
    """Convert GEE/network/service failures into structured unavailable results."""

    def execute(self, operation, *, stage, validator=None):
        try:
            value = operation()
        except Exception as exc:
            return self.failure(stage, exc)
        if validator is not None:
            try:
                valid = validator(value)
            except Exception as exc:
                return self.failure(stage, exc)
            if not valid:
                return self.failure(stage, "GEE operation returned an unusable result")
        return {
            "ok": True,
            "status": "AVAILABLE",
            "stage": stage,
            "value": value,
        }

    def failure(self, stage, error):
        reason = str(error)
        category = self._category(reason)
        return {
            "ok": False,
            "status": UNAVAILABLE,
            "validity_status": UNAVAILABLE,
            "stage": stage,
            "error_category": category,
            "reason": reason or "GEE operation failed without a reason",
        }

    @staticmethod
    def _category(reason):
        text = reason.lower()
        if "timeout" in text or "timed out" in text:
            return "TIMEOUT"
        if any(term in text for term in ("quota", "rate limit", "too many requests")):
            return "QUOTA_OR_RATE_LIMIT"
        if any(term in text for term in ("auth", "permission", "credentials", "unauthorized")):
            return "AUTHENTICATION_OR_PERMISSION"
        if any(term in text for term in ("network", "connection", "service unavailable", "503", "502")):
            return "NETWORK_OR_SERVICE"
        if any(term in text for term in ("empty", "no imagery", "no image", "unusable")):
            return "EMPTY_OR_UNUSABLE_RESULT"
        return "PROCESSING_ERROR"


def unavailable_observation(region, reason, *, stage="GEE_PROCESSING", legacy_status="ERROR"):
    """Build an observation envelope that downstream gates cannot treat as valid."""
    return {
        "status": legacy_status,
        "validity_status": UNAVAILABLE,
        "region": region,
        "reason": reason,
        "reliability": {
            "status": UNAVAILABLE,
            "stage": stage,
            "reason": reason,
        },
        "provenance": provenance(
            UNAVAILABLE,
            source="Google Earth Engine",
            method="Reliability-layer failure handling",
            limitations=["No usable satellite observation was produced"],
        ),
        "satellite": {
            "status": UNAVAILABLE,
            "validity_status": UNAVAILABLE,
            "region": region,
            "water_area": None,
        },
        "decision_support": {
            "status": UNAVAILABLE,
            "reason": reason,
            "risk_available": False,
        },
    }


def merge_reliability_metadata(observation, failure):
    """Attach a normalized reliability failure without mutating the input."""
    result = deepcopy(observation)
    result["validity_status"] = UNAVAILABLE
    result["reliability"] = {
        key: value for key, value in failure.items() if key != "value"
    }
    result.setdefault("satellite", {})["validity_status"] = UNAVAILABLE
    result.setdefault("satellite", {})["status"] = UNAVAILABLE
    result["decision_support"] = {
        "status": UNAVAILABLE,
        "reason": failure.get("reason"),
        "risk_available": False,
    }
    return result