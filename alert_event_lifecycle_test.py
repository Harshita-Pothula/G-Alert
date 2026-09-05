"""Focused tests for the durable alert event lifecycle."""

import os
import tempfile

from alert_event_lifecycle import (
    ACKNOWLEDGED,
    CREATED,
    EVIDENCE_SNAPSHOT_TAKEN,
    RESOLVED,
    AlertCreationRejected,
    AlertEventLifecycleManager,
    DuplicateActiveAlert,
    InvalidAlertTransition,
)


def _warning_assessment():
    return {
        "risk_level": "WARNING",
        "assessment_status": "COMPLETE",
        "confidence": "PROTOTYPE_LIMITED",
        "risk_score": 0.42,
        "observed_evidence": ["verified satellite and sensor evidence"],
        "derived_indicators": [{"name": "temporal_change", "value": 0.2}],
        "simulated_signals": [],
        "unavailable_information": [],
        "provenance": {"type": "DERIVED_FROM_REAL_DATA", "source": "test"},
    }


def _evidence_snapshot():
    return {
        "region": "Tsho_Rolpa_Nepal",
        "satellite": {
            "image_id": "sentinel-image-1",
            "acquisition_time": "2026-09-01T05:00:00+00:00",
        },
        "sensors": {
            "vibration_cmps": 18.2,
            "water_level_cm": 182.0,
        },
        "provenance": {
            "type": "DERIVED_FROM_REAL_DATA",
            "source": "sentinel-image-1 and deployed sensors",
        },
    }


def _manager():
    directory = tempfile.TemporaryDirectory()
    path = os.path.join(directory.name, "alerts.sqlite3")
    return directory, path


def test_state_transitions_and_invalid_transitions():
    directory, path = _manager()
    try:
        manager = AlertEventLifecycleManager(path)
        alert = manager.create_alert(_warning_assessment(), _evidence_snapshot())
        assert alert["state"] == CREATED
        assert manager.take_evidence_snapshot(alert["alert_id"])["state"] == EVIDENCE_SNAPSHOT_TAKEN
        assert manager.acknowledge(alert["alert_id"])["state"] == ACKNOWLEDGED
        assert manager.resolve(alert["alert_id"])["state"] == RESOLVED
        try:
            manager.acknowledge(alert["alert_id"])
        except InvalidAlertTransition:
            pass
        else:
            raise AssertionError("resolved alert accepted an invalid transition")
    finally:
        directory.cleanup()


def test_snapshot_is_immutable_and_traceable():
    directory, path = _manager()
    try:
        manager = AlertEventLifecycleManager(path)
        assessment = _warning_assessment()
        evidence = _evidence_snapshot()
        alert = manager.create_alert(assessment, evidence)
        evidence["sensors"]["water_level_cm"] = 999
        assessment["risk_score"] = 0
        stored = manager.get_alert(alert["alert_id"])["evidence_snapshot"]
        assert stored["evidence"]["sensors"]["water_level_cm"] == 182.0
        assert stored["assessment"]["risk_score"] == 0.42
        assert stored["evidence"]["satellite"]["image_id"] == "sentinel-image-1"
        assert stored["provenance"]["type"] == "DERIVED_FROM_REAL_DATA"
    finally:
        directory.cleanup()


def test_persistence_survives_manager_restart():
    directory, path = _manager()
    try:
        first = AlertEventLifecycleManager(path)
        alert = first.create_alert(_warning_assessment(), _evidence_snapshot())
        second = AlertEventLifecycleManager(path)
        restored = second.get_alert(alert["alert_id"])
        assert restored["state"] == CREATED
        assert restored["evidence_snapshot"]["evidence"]["satellite"]["image_id"] == "sentinel-image-1"
    finally:
        directory.cleanup()


def test_duplicate_active_alert_is_blocked_but_resolved_alert_allows_new_event():
    directory, path = _manager()
    try:
        manager = AlertEventLifecycleManager(path)
        first = manager.create_alert(_warning_assessment(), _evidence_snapshot())
        try:
            manager.create_alert(_warning_assessment(), _evidence_snapshot())
        except DuplicateActiveAlert:
            pass
        else:
            raise AssertionError("duplicate active alert was accepted")
        manager.take_evidence_snapshot(first["alert_id"])
        manager.acknowledge(first["alert_id"])
        manager.resolve(first["alert_id"])
        second = manager.create_alert(_warning_assessment(), _evidence_snapshot())
        assert second["alert_id"] != first["alert_id"]
    finally:
        directory.cleanup()


def test_unverified_warning_cannot_create_alert():
    directory, path = _manager()
    try:
        manager = AlertEventLifecycleManager(path)
        invalid = _warning_assessment()
        invalid["assessment_status"] = "LIMITED_CONFIDENCE"
        try:
            manager.create_alert(invalid, _evidence_snapshot())
        except AlertCreationRejected:
            pass
        else:
            raise AssertionError("unverified warning created an alert")
    finally:
        directory.cleanup()


if __name__ == "__main__":
    test_state_transitions_and_invalid_transitions()
    test_snapshot_is_immutable_and_traceable()
    test_persistence_survives_manager_restart()
    test_duplicate_active_alert_is_blocked_but_resolved_alert_allows_new_event()
    test_unverified_warning_cannot_create_alert()
    print("Alert event lifecycle tests: PASS")