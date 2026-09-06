"""Focused tests for critical warning and alert audit reconstruction."""

import os
import sqlite3
import tempfile

from alert_event_lifecycle import (
    AlertEventLifecycleManager,
)
from audit_trail import AuditTrail


def _assessment():
    return {
        "risk_level": "WARNING",
        "assessment_status": "COMPLETE",
        "decision_support_status": "MULTI_SIGNAL",
        "confidence": "PROTOTYPE_LIMITED",
        "risk_score": 0.42,
        "action": "Increase monitoring and review observations",
        "explanation": "Satellite change and sensor readings support warning review",
        "observed_evidence": ["verified Sentinel-2 and sensor evidence"],
        "derived_indicators": [{"name": "temporal_change", "value": 0.2}],
        "assumptions": ["Prototype thresholds are not validated GLOF probabilities"],
        "simulated_signals": [],
        "unavailable_information": [],
        "meta_flag": "decision support only",
    }


def _evidence():
    return {
        "observation_id": "observation-123",
        "recorded_at": "2026-09-05T05:00:00+00:00",
        "region": "Tsho_Rolpa_Nepal",
        "satellite": {
            "status": "SUCCESS",
            "image_id": "sentinel-image-123",
            "acquisition_time": "2026-09-04T05:00:00+00:00",
            "data_quality": {"confidence": 0.86, "valid_pixel_fraction": 0.91},
        },
        "sensors": {"vibration_cmps": 18.2, "water_level_cm": 182.0},
        "identity_status": "IDENTITY_SUPPORTED",
        "provenance": {
            "type": "DERIVED_FROM_REAL_DATA",
            "source": "Sentinel-2 and verified sensor evidence",
        },
    }


def test_warning_and_alert_lifecycle_are_audited_and_reconstructable():
    directory = tempfile.TemporaryDirectory()
    try:
        alert_db = os.path.join(directory.name, "alerts.sqlite3")
        audit_db = os.path.join(directory.name, "audit.sqlite3")
        manager = AlertEventLifecycleManager(alert_db, audit_database_path=audit_db)
        alert = manager.create_alert(_assessment(), _evidence())
        manager.take_evidence_snapshot(alert["alert_id"])
        manager.acknowledge(alert["alert_id"])
        manager.resolve(alert["alert_id"])

        events = manager.audit_trail.list_for_alert(alert["alert_id"])
        assert [event["event_type"] for event in events] == [
            "WARNING_VERIFIED",
            "ALERT_CREATED",
            "ALERT_EVIDENCE_SNAPSHOT_TAKEN",
            "ALERT_ACKNOWLEDGED",
            "ALERT_RESOLVED",
        ]
        reconstructed = manager.audit_trail.reconstruct(events[0]["audit_id"])
        assert reconstructed["why"] == "Verified WARNING assessment created an alert"
        assert reconstructed["observation"]["observation_id"] == "observation-123"
        assert reconstructed["satellite"]["image_id"] == "sentinel-image-123"
        assert reconstructed["satellite"]["acquisition_time"] == "2026-09-04T05:00:00+00:00"
        assert reconstructed["sensors"]["water_level_cm"] == 182.0
        assert reconstructed["data_quality"]["confidence"] == 0.86
        assert reconstructed["validity"]["identity_status"] == "IDENTITY_SUPPORTED"
        assert reconstructed["assumptions"]
        assert reconstructed["provenance"]["type"] == "DERIVED_FROM_REAL_DATA"
        assert reconstructed["decision_support"]["risk_level"] == "WARNING"
        assert reconstructed["resulting_state"] == "CREATED"
    finally:
        directory.cleanup()


def test_audit_records_are_append_only():
    directory = tempfile.TemporaryDirectory()
    try:
        audit_db = os.path.join(directory.name, "audit.sqlite3")
        trail = AuditTrail(audit_db)
        record = trail.record(
            "WARNING_VERIFIED",
            assessment=_assessment(),
            evidence_snapshot=_evidence(),
            provenance=_evidence()["provenance"],
            resulting_state="CREATED",
        )
        connection = sqlite3.connect(audit_db)
        try:
            try:
                connection.execute(
                    "UPDATE audit_events SET resulting_state = 'MUTATED' WHERE audit_id = ?",
                    (record["audit_id"],),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
            else:
                raise AssertionError("audit record was silently updated")
        finally:
            connection.close()
        assert trail.get(record["audit_id"])["resulting_state"] == "CREATED"
    finally:
        directory.cleanup()


if __name__ == "__main__":
    test_warning_and_alert_lifecycle_are_audited_and_reconstructable()
    test_audit_records_are_append_only()
    print("Audit trail tests: PASS")