"""Durable lifecycle management for verified G-ALERT warning events."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from audit_trail import AuditTrail
from region_integrity import require_region_match, require_valid_region


CREATED = "CREATED"
EVIDENCE_SNAPSHOT_TAKEN = "EVIDENCE_SNAPSHOT_TAKEN"
ACKNOWLEDGED = "ACKNOWLEDGED"
RESOLVED = "RESOLVED"

NEWLY_DETECTED = "NEWLY_DETECTED"
PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
CONFIRMED = "CONFIRMED"
PERSISTENT = "PERSISTENT"
NO_ACTIVE_WARNING = "NO_ACTIVE_WARNING"

ALERT_STATES = {
    CREATED,
    EVIDENCE_SNAPSHOT_TAKEN,
    ACKNOWLEDGED,
    RESOLVED,
}

ALLOWED_TRANSITIONS = {
    CREATED: {EVIDENCE_SNAPSHOT_TAKEN},
    EVIDENCE_SNAPSHOT_TAKEN: {ACKNOWLEDGED},
    ACKNOWLEDGED: {RESOLVED},
    RESOLVED: set(),
}


class AlertLifecycleError(Exception):
    """Base exception for alert lifecycle failures."""


class AlertCreationRejected(AlertLifecycleError):
    """Raised when an assessment is not eligible to create an alert."""


class DuplicateActiveAlert(AlertLifecycleError):
    """Raised when an active alert already exists for the condition."""


class InvalidAlertTransition(AlertLifecycleError):
    """Raised when a requested state transition is not allowed."""


class AlertNotFound(AlertLifecycleError):
    """Raised when an alert identifier is not present in storage."""


def evaluate_warning_confirmation(
    current_observation,
    historical_observations=None,
    *,
    confirmation_observations=3,
    persistent_observations=4,
):
    """Classify warning persistence without recalculating risk.

    Historical observations are expected newest first. The current observation
    is evaluated separately so a just-persisted envelope can be compared with
    the prior stored evidence without creating a duplicate observation.
    """
    from early_warning_status import evaluate_early_warning_status

    historical_observations = historical_observations or []
    current_status = (current_observation or {}).get("early_warning_status") or {}
    current_status = current_status.get("status") or evaluate_early_warning_status(
        current_observation or {}
    ).get("status")
    previous_warning_observations = []
    for record in historical_observations:
        observation = record.get("observation", record)
        status_result = observation.get("early_warning_status") or evaluate_early_warning_status(observation)
        if status_result.get("status") == "WARNING":
            previous_warning_observations.append({
                "observation_id": record.get("observation_id") or observation.get("observation_id"),
                "acquisition_time": (observation.get("satellite") or {}).get("acquisition_time"),
                "risk": observation.get("risk") or {},
                "satellite_change": observation.get("satellite_change") or {},
            })
        else:
            break

    current_id = (current_observation or {}).get("observation_id")
    evidence_ids = [item.get("observation_id") for item in previous_warning_observations]
    if current_id:
        evidence_ids.insert(0, current_id)
    consecutive_count = len(previous_warning_observations) + (1 if current_status == "WARNING" else 0)
    required_confirmation = max(3, int(confirmation_observations))
    required_persistence = max(required_confirmation, int(persistent_observations))

    if current_status != "WARNING":
        prior_warning = bool(previous_warning_observations)
        state = "RESOLVED" if prior_warning and current_status in {"NORMAL", "WATCH"} else NO_ACTIVE_WARNING
        return {
            "state": state,
            "warning_status": current_status,
            "consecutive_warning_observations": 0,
            "required_confirmation_observations": required_confirmation,
            "required_persistent_observations": required_persistence,
            "confirmed": False,
            "persistent": False,
            "evidence_observation_ids": evidence_ids,
            "reason": (
                "The previous warning condition is no longer present."
                if state == "RESOLVED"
                else "No current confirmed warning condition is present."
            ),
        }

    current_change = (current_observation or {}).get("satellite_change") or {}
    worsening = current_change.get("trend") == "INCREASING"
    confirmed = consecutive_count >= required_confirmation
    persistent = consecutive_count >= required_persistence or (
        consecutive_count >= required_confirmation and worsening
    )
    state = PERSISTENT if persistent else CONFIRMED if confirmed else (
        PENDING_CONFIRMATION if previous_warning_observations else NEWLY_DETECTED
    )
    return {
        "state": state,
        "warning_status": current_status,
        "consecutive_warning_observations": consecutive_count,
        "required_confirmation_observations": required_confirmation,
        "required_persistent_observations": required_persistence,
        "confirmed": confirmed,
        "persistent": persistent,
        "worsening_condition": worsening,
        "evidence_observation_ids": evidence_ids,
        "reason": (
            "The warning has persisted across repeated valid observations."
            if persistent
            else "The warning is confirmed by repeated observations."
            if confirmed
            else "A warning-level observation requires another observation for confirmation."
            if state == PENDING_CONFIRMATION
            else "A new warning-level observation has been detected and is awaiting confirmation."
        ),
    }


class AlertEventLifecycleManager:
    """Persist and transition verified warning events without changing observation storage."""

    def __init__(self, database_path=None, audit_database_path=None, audit_trail=None):
        configured_path = database_path or os.getenv(
            "G_ALERT_ALERTS_DB",
            os.getenv("G_ALERT_OBSERVATIONS_DB", "g_alert_observations.sqlite3"),
        )
        self.database_path = Path(configured_path)
        if self.database_path.parent != Path("."):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        default_audit_path = self.database_path.with_name(
            f"{self.database_path.stem}_audit.sqlite3"
        )
        self.audit_trail = audit_trail or AuditTrail(
            audit_database_path or default_audit_path
        )
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self):
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_events (
                    alert_id TEXT PRIMARY KEY,
                    region TEXT NOT NULL,
                    condition_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_events_active_condition
                ON alert_events(region, condition_key)
                WHERE state != 'RESOLVED'
                """
            )

    @staticmethod
    def _validate_warning(assessment, evidence_snapshot):
        if not isinstance(assessment, dict):
            raise AlertCreationRejected("assessment must be a dictionary")
        if assessment.get("risk_level") != "WARNING":
            raise AlertCreationRejected("only a WARNING assessment may create an alert")
        if assessment.get("assessment_status") != "COMPLETE":
            raise AlertCreationRejected("warning assessment is not verified as COMPLETE")
        if assessment.get("simulated_signals"):
            raise AlertCreationRejected("simulated evidence cannot create an alert")
        if assessment.get("unavailable_information"):
            raise AlertCreationRejected("unavailable evidence cannot create an alert")
        if not assessment.get("observed_evidence"):
            raise AlertCreationRejected("warning lacks explicit observed evidence")
        if not isinstance(evidence_snapshot, dict):
            raise AlertCreationRejected("evidence_snapshot must be a dictionary")

    @staticmethod
    def _validate_provenance(snapshot_provenance):
        if not isinstance(snapshot_provenance, dict):
            raise AlertCreationRejected("alert evidence requires provenance")
        provenance_type = snapshot_provenance.get("type")
        if provenance_type in {None, "UNKNOWN", "UNAVAILABLE"}:
            raise AlertCreationRejected("alert evidence provenance is unavailable")

    def create_alert(
        self,
        assessment,
        evidence_snapshot,
        *,
        region=None,
        condition_key=None,
        provenance=None,
    ):
        """Create one durable alert with an immutable evidence snapshot."""
        self._validate_warning(assessment, evidence_snapshot)
        snapshot_provenance = (
            provenance
            or evidence_snapshot.get("provenance")
            or assessment.get("provenance")
        )
        self._validate_provenance(snapshot_provenance)

        snapshot_region = evidence_snapshot.get("region")
        alert_region = region or snapshot_region
        try:
            require_valid_region(alert_region)
            require_region_match(alert_region, snapshot_region, "evidence_snapshot.region")
            if assessment.get("region") is not None:
                require_region_match(alert_region, assessment.get("region"), "assessment.region")
        except ValueError as exc:
            raise AlertCreationRejected(str(exc)) from exc
        alert_condition_key = condition_key or f"{alert_region}:WARNING"
        captured_at = datetime.now(timezone.utc).isoformat()
        snapshot = {
            "captured_at": captured_at,
            "assessment": deepcopy(assessment),
            "evidence": deepcopy(evidence_snapshot),
            "provenance": deepcopy(snapshot_provenance),
        }
        snapshot_json = json.dumps(snapshot, sort_keys=True, allow_nan=False)
        alert_id = str(uuid.uuid4())

        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO alert_events (
                        alert_id, region, condition_key, state,
                        created_at, updated_at, snapshot_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        alert_id,
                        alert_region,
                        alert_condition_key,
                        CREATED,
                        captured_at,
                        captured_at,
                        snapshot_json,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateActiveAlert(
                f"an active alert already exists for {alert_region}/{alert_condition_key}"
            ) from exc
        alert = self.get_alert(alert_id)
        snapshot = alert["evidence_snapshot"]
        self.audit_trail.record(
            "WARNING_VERIFIED",
            alert_id=alert_id,
            region=alert_region,
            assessment=assessment,
            evidence_snapshot=snapshot["evidence"],
            provenance=snapshot["provenance"],
            resulting_state=CREATED,
            reason="Verified WARNING assessment created an alert",
        )
        self.audit_trail.record(
            "ALERT_CREATED",
            alert_id=alert_id,
            region=alert_region,
            assessment=assessment,
            evidence_snapshot=snapshot["evidence"],
            provenance=snapshot["provenance"],
            resulting_state=CREATED,
            reason="Alert lifecycle event created",
        )
        return alert

    def transition(self, alert_id, target_state):
        """Apply exactly one allowed lifecycle transition."""
        if target_state not in ALERT_STATES:
            raise InvalidAlertTransition(f"unknown target state: {target_state}")
        alert = self.get_alert(alert_id)
        current_state = alert["state"]
        if target_state not in ALLOWED_TRANSITIONS[current_state]:
            raise InvalidAlertTransition(
                f"cannot transition {current_state} to {target_state}"
            )
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            connection.execute(
                "UPDATE alert_events SET state = ?, updated_at = ? WHERE alert_id = ?",
                (target_state, updated_at, alert_id),
            )
        updated_alert = self.get_alert(alert_id)
        snapshot = updated_alert["evidence_snapshot"]
        event_type = {
            EVIDENCE_SNAPSHOT_TAKEN: "ALERT_EVIDENCE_SNAPSHOT_TAKEN",
            ACKNOWLEDGED: "ALERT_ACKNOWLEDGED",
            RESOLVED: "ALERT_RESOLVED",
        }[target_state]
        self.audit_trail.record(
            event_type,
            alert_id=alert_id,
            region=updated_alert["region"],
            assessment=snapshot["assessment"],
            evidence_snapshot=snapshot["evidence"],
            provenance=snapshot["provenance"],
            resulting_state=target_state,
            reason=f"Alert lifecycle transitioned to {target_state}",
        )
        return updated_alert

    def take_evidence_snapshot(self, alert_id):
        return self.transition(alert_id, EVIDENCE_SNAPSHOT_TAKEN)

    def acknowledge(self, alert_id):
        return self.transition(alert_id, ACKNOWLEDGED)

    def resolve(self, alert_id):
        return self.transition(alert_id, RESOLVED)

    def get_alert(self, alert_id):
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT alert_id, region, condition_key, state,
                       created_at, updated_at, snapshot_json
                FROM alert_events
                WHERE alert_id = ?
                """,
                (alert_id,),
            ).fetchone()
        if row is None:
            raise AlertNotFound(f"alert not found: {alert_id}")
        record = {key: row[key] for key in row.keys() if key != "snapshot_json"}
        record["evidence_snapshot"] = json.loads(row["snapshot_json"])
        return record

    def list_alerts(self, region=None, limit=50):
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer from 1 to 500")
        query = """
            SELECT alert_id, region, condition_key, state,
                   created_at, updated_at, snapshot_json
            FROM alert_events
        """
        parameters = []
        if region is not None:
            query += " WHERE region = ?"
            parameters.append(region)
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(limit)
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        records = []
        for row in rows:
            record = {key: row[key] for key in row.keys() if key != "snapshot_json"}
            record["evidence_snapshot"] = json.loads(row["snapshot_json"])
            records.append(record)
        return records