"""Append-only audit records for critical G-ALERT decisions."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


class AuditTrailError(Exception):
    """Base exception for audit trail failures."""


class AuditTrail:
    """Store immutable decision explanations in a separate SQLite database."""

    def __init__(self, database_path=None):
        configured_path = database_path or os.getenv(
            "G_ALERT_AUDIT_DB", "g_alert_audit.sqlite3"
        )
        self.database_path = Path(configured_path)
        if self.database_path.parent != Path("."):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    alert_id TEXT,
                    region TEXT,
                    resulting_state TEXT,
                    decision_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_alert_time "
                "ON audit_events(alert_id, event_at DESC)"
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS prevent_audit_update
                BEFORE UPDATE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit events are append-only');
                END
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS prevent_audit_delete
                BEFORE DELETE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit events are append-only');
                END
                """
            )

    def record(
        self,
        event_type,
        *,
        alert_id=None,
        region=None,
        assessment,
        evidence_snapshot,
        provenance,
        resulting_state,
        reason=None,
    ):
        """Append one complete decision explanation and return its identifier."""
        if not event_type:
            raise AuditTrailError("event_type is required")
        if not isinstance(assessment, dict):
            raise AuditTrailError("assessment must be a dictionary")
        if not isinstance(evidence_snapshot, dict):
            raise AuditTrailError("evidence_snapshot must be a dictionary")
        if not isinstance(provenance, dict):
            raise AuditTrailError("provenance must be a dictionary")

        event_at = datetime.now(timezone.utc).isoformat()
        evidence = deepcopy(evidence_snapshot)
        assessment_copy = deepcopy(assessment)
        decision = {
            "why": reason or assessment_copy.get("explanation"),
            "observation": {
                "observation_id": evidence.get("observation_id"),
                "recorded_at": evidence.get("recorded_at"),
                "region": evidence.get("region") or region,
            },
            "satellite": deepcopy(evidence.get("satellite")),
            "sensors": deepcopy(evidence.get("sensors")),
            "data_quality": deepcopy(
                evidence.get("data_quality")
                or (evidence.get("satellite") or {}).get("data_quality")
            ),
            "validity": deepcopy({
                "assessment_status": assessment_copy.get("assessment_status"),
                "decision_support_status": assessment_copy.get("decision_support_status"),
                "identity_status": evidence.get("identity_status")
                or (evidence.get("temporal_evidence") or {}).get("identity_status")
                or ((evidence.get("satellite") or {}).get("candidate_detection") or {}).get("identity_status"),
                "satellite_status": (evidence.get("satellite") or {}).get("status"),
            }),
            "assumptions": deepcopy(assessment_copy.get("assumptions", [])),
            "unavailable_information": deepcopy(
                assessment_copy.get("unavailable_information", [])
            ),
            "provenance": deepcopy(provenance),
            "decision_support": deepcopy({
                "risk_level": assessment_copy.get("risk_level"),
                "risk_score": assessment_copy.get("risk_score"),
                "confidence": assessment_copy.get("confidence"),
                "action": assessment_copy.get("action"),
                "meta_flag": assessment_copy.get("meta_flag"),
            }),
            "resulting_state": resulting_state,
            "assessment": assessment_copy,
            "evidence_snapshot": evidence,
        }
        decision_json = json.dumps(decision, sort_keys=True, allow_nan=False)
        audit_id = str(uuid.uuid4())
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    audit_id, event_type, event_at, alert_id,
                    region, resulting_state, decision_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    event_type,
                    event_at,
                    alert_id,
                    region,
                    resulting_state,
                    decision_json,
                ),
            )
        return self.get(audit_id)

    def get(self, audit_id):
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT audit_id, event_type, event_at, alert_id,
                       region, resulting_state, decision_json
                FROM audit_events
                WHERE audit_id = ?
                """,
                (audit_id,),
            ).fetchone()
        if row is None:
            raise AuditTrailError(f"audit event not found: {audit_id}")
        record = {key: row[key] for key in row.keys() if key != "decision_json"}
        record["decision"] = json.loads(row["decision_json"])
        return record

    def list_for_alert(self, alert_id):
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT audit_id, event_type, event_at, alert_id,
                       region, resulting_state, decision_json
                FROM audit_events
                WHERE alert_id = ?
                ORDER BY event_at ASC, audit_id ASC
                """,
                (alert_id,),
            ).fetchall()
        records = []
        for row in rows:
            record = {key: row[key] for key in row.keys() if key != "decision_json"}
            record["decision"] = json.loads(row["decision_json"])
            records.append(record)
        return records

    def reconstruct(self, audit_id):
        """Return the complete logical decision explanation for one audit event."""
        record = self.get(audit_id)
        return {
            "audit_id": record["audit_id"],
            "event_type": record["event_type"],
            "event_at": record["event_at"],
            "alert_id": record["alert_id"],
            "region": record["region"],
            "resulting_state": record["resulting_state"],
            **record["decision"],
        }