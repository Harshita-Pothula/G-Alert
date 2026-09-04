"""Phase 1 tests: YOLO GLOF contribution, history, and integrated JSON shape.

Does not call Google Earth Engine or load YOLOv8 weights.
"""

from ai.yolov8_detector import Detection
from main import (
    INTEGRATED_RESULT_KEYS,
    _attach_risk_and_history,
    _integrated_result_skeleton,
    glof_ai_signal_for_risk,
    run_integrated_monitoring,
)
from risk_engine import RiskEngine


def _assert_shape(result, label):
    missing = [key for key in INTEGRATED_RESULT_KEYS if key not in result]
    if missing:
        raise AssertionError(f"{label} missing keys: {missing}")


def test_no_domain_signal_ai_contribution_is_zero():
    print("A. NO_DOMAIN_SIGNAL -> ai_signal == 0.0")
    signal = glof_ai_signal_for_risk("NO_DOMAIN_SIGNAL")
    print(f"   glof_ai_signal_for_risk(NO_DOMAIN_SIGNAL)={signal}")
    if signal != 0.0:
        raise AssertionError("NO_DOMAIN_SIGNAL must contribute 0.0 to GLOF risk")

    unavailable = glof_ai_signal_for_risk("NOT_AVAILABLE")
    if unavailable != 0.0:
        raise AssertionError("Unavailable YOLO must contribute 0.0 to GLOF risk")

    engine = RiskEngine()
    generic_detections = [
        Detection(class_id=5, class_name="bus", confidence=0.95, bbox=[0, 0, 10, 10]),
        Detection(class_id=0, class_name="person", confidence=0.9, bbox=[1, 1, 8, 8]),
    ]
    generic_signal = engine.calculate_ai_signal(generic_detections)
    print(f"   calculate_ai_signal(generic COCO detections)={generic_signal} (not used for GLOF)")
    if generic_signal <= 0:
        raise AssertionError("Sanity: generic detections would have been a non-zero engine AI signal")

    inflated = engine.assess_risk(satellite_signal=0.0, ai_signal=generic_signal, sensor_signal=0.0)
    honest = engine.assess_risk(satellite_signal=0.0, ai_signal=signal, sensor_signal=0.0)
    print(f"   risk if generic YOLO were used={inflated['risk_score']} vs honest={honest['risk_score']}")
    if honest["signals"]["ai"] != 0.0:
        raise AssertionError("Honest GLOF path must record ai signal 0.0")
    if honest["risk_score"] >= inflated["risk_score"]:
        raise AssertionError("Zeroing NO_DOMAIN_SIGNAL should not inflate risk vs generic YOLO")
    print("   PASS")


def test_history_in_integrated_result():
    print("B. Integrated result contains history")
    result = _integrated_result_skeleton("Tsho_Rolpa_Nepal", status="SUCCESS")
    engine = RiskEngine()
    _attach_risk_and_history(
        result,
        engine,
        satellite_signal=0.2,
        ai_signal=glof_ai_signal_for_risk("NO_DOMAIN_SIGNAL"),
        sensor_signal=0.0,
        region_key="Tsho_Rolpa_Nepal",
    )
    if "history" not in result:
        raise AssertionError("history key missing")
    if not isinstance(result["history"], list) or len(result["history"]) != 1:
        raise AssertionError(f"expected history length 1, got {result.get('history')}")
    if result["risk"] is None or "action" not in result["risk"] or "explanation" not in result["risk"]:
        raise AssertionError("warning/action must remain inside risk")
    if result["history"][0]["region"] != "Tsho_Rolpa_Nepal":
        raise AssertionError("history entry should include region")
    print(f"   history length={len(result['history'])} risk_level={result['risk']['risk_level']}")
    print("   PASS")


def test_json_shape_success_and_error():
    print("C. Integrated success/error JSON keys")
    error_result = run_integrated_monitoring("not_a_real_region")
    _assert_shape(error_result, "error")
    if error_result["status"] != "ERROR":
        raise AssertionError(f"unknown region should be ERROR, got {error_result['status']}")
    if error_result["risk"] is not None:
        raise AssertionError("error path should not invent a risk assessment")
    if error_result["history"] != []:
        raise AssertionError("error path should use empty history, not invented events")
    if error_result["downstream_exposure"] is not None:
        raise AssertionError("unknown region should not invent downstream exposure")
    if error_result["ai"].get("signal") != 0.0:
        raise AssertionError("error path AI signal must be 0.0")

    success_like = _integrated_result_skeleton("Imja_Tsho_Nepal", status="SUCCESS")
    engine = RiskEngine()
    _attach_risk_and_history(success_like, engine, 0.1, 0.0, 0.0, "Imja_Tsho_Nepal")
    _assert_shape(success_like, "success")
    if success_like["downstream_exposure"] is None:
        raise AssertionError("Imja_Tsho_Nepal should keep catalog downstream_exposure")
    print("   error keys OK; success skeleton keys OK")
    print("   PASS")


if __name__ == "__main__":
    print("G-ALERT Phase 1 integrated tests")
    print("-" * 40)
    test_no_domain_signal_ai_contribution_is_zero()
    print()
    test_history_in_integrated_result()
    print()
    test_json_shape_success_and_error()
    print("-" * 40)
    print("Test result: PASS")
