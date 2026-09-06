"""Phase 1 telemetry validation for future G-ALERT sensor integrations."""

import hashlib
import json
import math
from datetime import datetime, timezone

from region_integrity import RegionIntegrityError, require_valid_region


SUPPORTED_SENSOR_TYPES = {"vibration", "water_level", "rainfall"}
HEALTH_ONLINE = "ONLINE"
HEALTH_STALE = "STALE"
HEALTH_INVALID = "INVALID"
HEALTH_UNKNOWN = "UNKNOWN"

_UNIT_OPTIONS = {
    "vibration": {"cm/s", "cm/s2", "cm/s^2", "cm/s²"},
    "water_level": {"cm", "m"},
    "rainfall": {"mm/h", "mm/hr", "mm/hour"},
}
_REQUIRED_FIELDS = ("sensor_id", "region_key", "sensor_type", "timestamp", "reading")


class SensorTelemetryService:
    """Validate telemetry and track Phase 1 duplicate/freshness/health state."""

    def __init__(self, stale_after_seconds=300, future_skew_seconds=30):
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        if future_skew_seconds < 0:
            raise ValueError("future_skew_seconds cannot be negative")
        self.stale_after_seconds = stale_after_seconds
        self.future_skew_seconds = future_skew_seconds
        self._seen_keys = set()
        self._health = {}

    def ingest(self, payload, now=None):
        """Validate one payload and return a JSON-safe ingestion result."""
        received_at = self._coerce_now(now)
        validation = self._validate_payload(payload, received_at)
        if not validation["valid"]:
            sensor_id = payload.get("sensor_id") if isinstance(payload, dict) else None
            if isinstance(sensor_id, str) and sensor_id:
                self._health[sensor_id] = {
                    "sensor_id": sensor_id,
                    "status": HEALTH_INVALID,
                    "last_timestamp": None,
                    "last_received_at": received_at.isoformat(),
                    "last_error": validation["errors"][0],
                }
            return {
                "ingestion_status": "REJECTED",
                "duplicate": False,
                "freshness": "INVALID",
                "sensor_status": HEALTH_INVALID,
                "errors": validation["errors"],
            }

        normalized = validation["payload"]
        duplicate_key = self._duplicate_key(normalized)
        if duplicate_key in self._seen_keys:
            sensor_id = normalized["sensor_id"]
            health = self._health.get(sensor_id, {})
            health.update({"sensor_id": sensor_id, "status": health.get("status", HEALTH_UNKNOWN)})
            self._health[sensor_id] = health
            return {
                "ingestion_status": "DUPLICATE",
                "duplicate": True,
                "freshness": validation["freshness"],
                "sensor_status": health["status"],
                "payload": normalized,
            }

        self._seen_keys.add(duplicate_key)
        sensor_status = HEALTH_ONLINE if validation["freshness"] == "FRESH" else HEALTH_STALE
        sensor_id = normalized["sensor_id"]
        self._health[sensor_id] = {
            "sensor_id": sensor_id,
            "region_key": normalized["region_key"],
            "sensor_type": normalized["sensor_type"],
            "status": sensor_status,
            "last_timestamp": normalized["timestamp"],
            "last_received_at": received_at.isoformat(),
            "last_error": None,
        }
        return {
            "ingestion_status": "ACCEPTED",
            "duplicate": False,
            "freshness": validation["freshness"],
            "sensor_status": sensor_status,
            "received_at": received_at.isoformat(),
            "payload": normalized,
        }

    def get_sensor_status(self, sensor_id, now=None):
        """Return current status, applying stale detection to the last reading."""
        health = self._health.get(sensor_id)
        if health is None:
            return {"sensor_id": sensor_id, "status": HEALTH_UNKNOWN}
        if health["status"] == HEALTH_ONLINE:
            current = self._coerce_now(now)
            timestamp = self._parse_timestamp(health["last_timestamp"])
            if timestamp is None or self._age_seconds(timestamp, current) > self.stale_after_seconds:
                health = dict(health)
                health["status"] = HEALTH_STALE
        return dict(health)

    def get_health_snapshot(self, now=None):
        """Return status for every sensor seen by this service instance."""
        return {
            sensor_id: self.get_sensor_status(sensor_id, now=now)
            for sensor_id in sorted(self._health)
        }

    def _validate_payload(self, payload, now):
        errors = []
        if not isinstance(payload, dict):
            return {"valid": False, "errors": ["payload must be a dictionary"]}

        for field in _REQUIRED_FIELDS:
            if field not in payload:
                errors.append(f"missing required field: {field}")
        if errors:
            return {"valid": False, "errors": errors}

        sensor_id = payload["sensor_id"]
        if not isinstance(sensor_id, str) or not sensor_id.strip():
            errors.append("sensor_id must be a non-empty string")

        region_key = payload["region_key"]
        try:
            require_valid_region(region_key)
        except (RegionIntegrityError, TypeError) as exc:
            errors.append(str(exc))

        sensor_type = payload["sensor_type"]
        if not isinstance(sensor_type, str) or sensor_type not in SUPPORTED_SENSOR_TYPES:
            errors.append(f"unsupported sensor_type: {sensor_type!r}")

        timestamp = payload["timestamp"]
        parsed_timestamp = self._parse_timestamp(timestamp)
        if parsed_timestamp is None:
            errors.append("timestamp must be a timezone-aware ISO-8601 UTC timestamp")
        else:
            age = self._age_seconds(parsed_timestamp, now)
            if age < -self.future_skew_seconds:
                errors.append("timestamp is too far in the future")

        reading = payload["reading"]
        if not isinstance(reading, dict):
            errors.append("reading must be a dictionary")
            reading = {}
        value = reading.get("value")
        unit = reading.get("unit")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append("reading.value must be a finite number")
        elif value < 0:
            errors.append("reading.value must not be negative")
        if sensor_type in _UNIT_OPTIONS and unit not in _UNIT_OPTIONS[sensor_type]:
            errors.append(f"reading.unit is invalid for sensor_type {sensor_type!r}")

        sequence = payload.get("sequence")
        if sequence is not None and (isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0):
            errors.append("sequence must be a non-negative integer when provided")

        if errors:
            return {"valid": False, "errors": errors}

        normalized = {
            "sensor_id": sensor_id.strip(),
            "region_key": region_key,
            "sensor_type": sensor_type,
            "timestamp": parsed_timestamp.isoformat().replace("+00:00", "Z"),
            "reading": {"value": value, "unit": unit},
        }
        if sequence is not None:
            normalized["sequence"] = sequence
        for field in ("device_id", "firmware_version"):
            if field in payload:
                normalized[field] = payload[field]
        age = self._age_seconds(parsed_timestamp, now)
        return {
            "valid": True,
            "payload": normalized,
            "freshness": "STALE" if age > self.stale_after_seconds else "FRESH",
        }

    @staticmethod
    def _parse_timestamp(value):
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _coerce_now(value):
        if value is None:
            return datetime.now(timezone.utc)
        if isinstance(value, datetime) and value.tzinfo is not None:
            return value.astimezone(timezone.utc)
        parsed = SensorTelemetryService._parse_timestamp(value)
        if parsed is None:
            raise ValueError("now must be a timezone-aware datetime or ISO-8601 timestamp")
        return parsed

    @staticmethod
    def _age_seconds(timestamp, now):
        return (now - timestamp).total_seconds()

    @staticmethod
    def _duplicate_key(payload):
        if "sequence" in payload:
            return ("sequence", payload["sensor_id"], payload["timestamp"], payload["sequence"])
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return ("hash", hashlib.sha256(canonical.encode("utf-8")).hexdigest())
