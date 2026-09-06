"""Phase 2 tests: Nepal simulation envelope, RiskEngine, history, honesty flags.

Does not call Google Earth Engine or load YOLOv8 weights.
"""

import os
import tempfile
from unittest.mock import patch

from main import (
    INTEGRATED_RESULT_KEYS,
    glof_ai_signal_for_risk,
    run_integrated_monitoring,
    run_nepal_simulation_sequence,
    run_nepal_simulation_step,
)
from simulation.nepal_disaster import NepalDisasterScenario


def _assert_shape(result, label):
    missing = [key for key in INTEGRATED_RESULT_KEYS if key not in result]
    if missing:
        raise AssertionError(f"{label} missing keys: {missing}")


def test_nepal_phases_and_engine_risk():
    print("A/B. Nepal phases + RiskEngine displayed risk")
    steps = run_nepal_simulation_sequence()
    phases = [step["simulation_phase"] for step in steps]
    expected_phases = ["NORMAL", "ALERT", "HIGH_ALERT", "CRITICAL", "INCIDENT"]
    if phases != expected_phases:
        raise AssertionError(f"phases={phases}")

    expected_engine = {
        "NORMAL": "SAFE",
        "ALERT": "SAFE",
        "HIGH_ALERT": "WARNING",
        "CRITICAL": "HIGH_RISK",
        "INCIDENT": "CRITICAL",
    }
    expected_action = {
        "SAFE": "Continue monitoring",
        "WARNING": "Increase monitoring and review observations",
        "HIGH_RISK": "Review downstream exposure and prepare warning",
        "CRITICAL": "Trigger emergency-warning workflow",
    }

    for step in steps:
        phase = step["simulation_phase"]
        risk = step["risk"]
        if risk is None:
            raise AssertionError("displayed risk must come from RiskEngine")
        level = risk["risk_level"]
        print(f"   {phase} → engine {level} score={risk['risk_score']} action={risk['action']}")
        if level != expected_engine[phase]:
            raise AssertionError(
                f"{phase}: expected engine {expected_engine[phase]}, got {level}"
            )
        if risk["action"] != expected_action[level]:
            raise AssertionError(f"{phase}: unexpected action {risk['action']}")
        if risk.get("source") != "prototype_demo_logic":
            raise AssertionError("risk.source should mark prototype demo logic")
    print("   PASS")
    return steps


def test_nepal_history_and_envelope(steps):
    print("C/D. Nepal history length 5 + Phase 1 JSON envelope")
    last = steps[-1]
    history = last["history"]
    if len(history) != 5:
        raise AssertionError(f"history length {len(history)}")
    history_phases = [entry.get("simulation_phase") for entry in history]
    if history_phases != ["NORMAL", "ALERT", "HIGH_ALERT", "CRITICAL", "INCIDENT"]:
        raise AssertionError(f"history phases={history_phases}")
    for i, entry in enumerate(history):
        if entry.get("risk_level") != steps[i]["risk"]["risk_level"]:
            raise AssertionError("history is not the RiskEngine assessments")
        if "risk_score" not in entry or "action" not in entry:
            raise AssertionError("history entry missing engine fields")
    for step in steps:
        _assert_shape(step, step["simulation_phase"])
        if step["mode"] != "nepal_simulation":
            raise AssertionError(f"mode={step['mode']}")
    print("   PASS")


def test_nepal_simulated_flags(steps):
    print("E/F. Nepal sensors and AI marked simulated")
    for step in steps:
        sensors = step["sensors"]
        ai = step["ai"]
        if sensors.get("simulated") is not True:
            raise AssertionError("sensors must set simulated=True")
        if sensors.get("status") != "simulated":
            raise AssertionError("sensors.status should be simulated")
        if ai.get("simulated") is not True:
            raise AssertionError("Nepal AI must set simulated=True")
        if ai.get("status") != "SIMULATED_SUPPORTING_SIGNAL":
            raise AssertionError("Nepal AI must not look like YOLO / NO_DOMAIN_SIGNAL")
        if ai.get("detector_type") == "generic_object_detector":
            raise AssertionError("Nepal AI must not be labelled as generic YOLO")
        if step["satellite"].get("simulated") is not True:
            raise AssertionError("simulated satellite values must be labelled")
        if "yolo" in str(ai.get("detector_type", "")).lower():
            raise AssertionError("Nepal AI must not be YOLO")
        explanation_sources = (step["risk"].get("explanation_detail") or {}).get("sources", {})
        if explanation_sources.get("satellite", {}).get("status") != "SIMULATED":
            raise AssertionError("simulation satellite explanation must be SIMULATED")
        if explanation_sources.get("sensor", {}).get("status") != "SIMULATED":
            raise AssertionError("simulation sensor explanation must be SIMULATED")
        if explanation_sources.get("ai", {}).get("status") != "SIMULATED":
            raise AssertionError("simulation AI explanation must be SIMULATED")
    print("   PASS")


def test_live_yolo_still_zero():
    print("G. Live generic YOLO NO_DOMAIN_SIGNAL still 0.0")
    if glof_ai_signal_for_risk("NO_DOMAIN_SIGNAL") != 0.0:
        raise AssertionError("Phase 1 AI safety undone")
    if glof_ai_signal_for_risk("NOT_AVAILABLE") != 0.0:
        raise AssertionError("unavailable YOLO must stay 0.0")
    print("   PASS")


def test_monitoring_does_not_invent_sensors():
    print("H. Monitoring mode does not invent sensor telemetry")
    with tempfile.TemporaryDirectory() as directory, patch.dict(
        os.environ,
        {"G_ALERT_OBSERVATIONS_DB": f"{directory}/observations.sqlite3"},
    ):
        error = run_integrated_monitoring("not_a_real_region")
        if error["sensors"].get("status") != "NOT_RUN":
            raise AssertionError("unknown region should not invent sensors")

        with patch("main.initialize_gee_pipeline", return_value=None):
            result = run_integrated_monitoring("Tsho_Rolpa_Nepal")
    if result["status"] != "ERROR":
        raise AssertionError(f"GEE failure should be ERROR, got {result['status']}")
    if result["sensors"].get("status") != "NOT_RUN":
        raise AssertionError("monitoring must not insert simulated sensors when GEE fails")
    if result["risk"] is not None:
        raise AssertionError("GEE failure must not invent a monitoring risk score")
    print("   PASS")


def test_nepal_works_without_gee():
    print("GEE independence: Nepal sequence does not call GEE")
    with patch("main.initialize_gee_pipeline", side_effect=AssertionError("GEE should not run")):
        scenario = NepalDisasterScenario()
        step = run_nepal_simulation_step(scenario)
    if step is None or step["simulation_phase"] != "NORMAL":
        raise AssertionError("Nepal step should work without GEE")
    print("   PASS")


if __name__ == "__main__":
    print("G-ALERT Phase 2 Nepal integration tests")
    print("-" * 40)
    steps = test_nepal_phases_and_engine_risk()
    print()
    test_nepal_history_and_envelope(steps)
    print()
    test_nepal_simulated_flags(steps)
    print()
    test_live_yolo_still_zero()
    print()
    test_monitoring_does_not_invent_sensors()
    print()
    test_nepal_works_without_gee()
    print("-" * 40)
    print("Test result: PASS")
