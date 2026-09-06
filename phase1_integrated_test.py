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


def test_weather_and_missing_sensor_are_separate():
    result = _integrated_result_skeleton("Imja_Tsho_Nepal", status="SUCCESS")
    engine = RiskEngine()
    _attach_risk_and_history(
        result, engine, 0.1, 0.0, None, "Imja_Tsho_Nepal",
        weather_signal=0.2, weather_signal_provided=True,
    )
    if result["risk"]["signals"]["weather"] != 0.2:
        raise AssertionError("weather signal should remain separate")
    if result["risk"]["signals"]["sensor"] is not None:
        raise AssertionError("missing sensor evidence must not become numeric zero")
    if result["risk"]["risk_level"] != "UNKNOWN":
        raise AssertionError("missing sensor evidence must not produce SAFE")
    print("   weather and missing sensor evidence remain separate")
    print("   PASS")


def test_explanation_detail_source_statuses_and_invariance():
    result = _integrated_result_skeleton("Imja_Tsho_Nepal", status="SUCCESS")
    result["satellite"]["status"] = "SUCCESS"
    result["weather"] = {
        "status": "SUCCESS",
        "source": "Open-Meteo",
        "rainfall_mmph": 0.2,
        "rainfall_24h_mm": 11.7,
        "provenance": {"type": "REAL_WEATHER_DATA", "source": "Open-Meteo"},
    }
    result["sensors"] = {
        "status": "STALE_TELEMETRY",
        "stale_readings": [{"sensor_id": "VIB-001"}],
        "readings": [],
        "simulated": False,
    }
    result["ai"] = {
        "status": "NO_DOMAIN_SIGNAL",
        "model": "yolov8n.pt",
        "detector_type": "generic_object_detector",
    }
    engine = RiskEngine()
    risk = engine.assess_risk(
        satellite_signal=0.5,
        ai_signal=0.0,
        sensor_signal=None,
        weather_signal=0.2,
        evidence={"explanation_sources": {
            "satellite": {"status": "SUCCESS"},
            "weather": {"status": "SUCCESS"},
            "sensor": {"status": "STALE_TELEMETRY"},
            "ai": {"status": "NO_DOMAIN_SIGNAL"},
        }},
    )
    expected_score = risk["risk_score"]
    detail = risk["explanation_detail"]
    if detail["sources"]["satellite"]["contributed"] is not True:
        raise AssertionError("positive satellite signal must be explained as contributing")
    if detail["sources"]["weather"]["contributed"] is not False:
        raise AssertionError("weather must remain separate from the weighted legacy score")
    if detail["sources"]["sensor"]["status"] != "STALE":
        raise AssertionError("stale telemetry must be explained as STALE")
    if detail["sources"]["ai"]["status"] != "NO_DOMAIN_SIGNAL":
        raise AssertionError("generic YOLO must be explained as NO_DOMAIN_SIGNAL")
    if "GLOF-domain" not in detail["sources"]["ai"]["summary"]:
        raise AssertionError("AI explanation must identify generic YOLO limitations")
    if risk["risk_score"] != expected_score:
        raise AssertionError("explanation generation changed the risk score")
    print("   explanation source statuses and score invariance PASS")


def test_tsho_rolpa_insufficient_explanation():
    result = _integrated_result_skeleton("Tsho_Rolpa_Nepal", status="SUCCESS")
    result["satellite"]["status"] = "IDENTITY_AMBIGUOUS"
    result["satellite"]["candidate_detection"] = {
        "identity_status": "IDENTITY_NOT_ESTABLISHED"
    }
    result["satellite"]["seasonal_comparison"] = {
        "status": "INSUFFICIENT_HISTORICAL_DATA"
    }
    engine = RiskEngine()
    _attach_risk_and_history(
        result, engine, 0.0, 0.0, None, "Tsho_Rolpa_Nepal",
        weather_signal=0.0, weather_signal_provided=True,
    )
    detail = result["risk"]["explanation_detail"]
    if result["risk"]["risk_level"] != "UNKNOWN":
        raise AssertionError("Tsho Rolpa must retain insufficient-evidence risk behavior")
    if detail["sources"]["satellite"]["status"] != "WITHHELD":
        raise AssertionError("Tsho Rolpa identity evidence must be explained as WITHHELD")
    if "definitive risk level" not in detail["summary"]:
        raise AssertionError("Tsho Rolpa explanation must state that no definitive assessment exists")
    print("   Tsho Rolpa insufficient explanation PASS")


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


def test_real_observed_evidence_is_lifecycle_compatible():
    result = _integrated_result_skeleton("Imja_Tsho_Nepal", status="SUCCESS")
    result["satellite"] = {
        "status": "SUCCESS",
        "provenance": {
            "type": "REAL_SATELLITE_DATA",
            "source": "Sentinel-2",
        },
        "seasonal_comparison": {"status": "VALID"},
    }
    result["weather"] = {
        "status": "SUCCESS",
        "source": "Open-Meteo",
        "provenance": {
            "type": "REAL_WEATHER_DATA",
            "source": "Open-Meteo",
        },
    }
    result["sensors"] = {
        "status": "PERSISTED_TELEMETRY",
        "simulated": False,
        "readings": [{"sensor_id": "VIB-001"}],
    }
    engine = RiskEngine()
    _attach_risk_and_history(
        result, engine, 0.4, 0.0, 0.3, "Imja_Tsho_Nepal",
        weather_signal=0.1, weather_signal_provided=True,
    )
    observed = result["risk"]["observed_evidence"]
    expected = {
        "real Sentinel-2 satellite evidence",
        "real Open-Meteo weather evidence",
        "fresh persisted IoT telemetry",
    }
    if set(observed) != expected:
        raise AssertionError(f"unexpected observed evidence: {observed}")
    print("   real observed evidence is lifecycle-compatible")
    print("   PASS")


if __name__ == "__main__":
    print("G-ALERT Phase 1 integrated tests")
    print("-" * 40)
    test_no_domain_signal_ai_contribution_is_zero()
    print()
    test_history_in_integrated_result()
    print()
    test_weather_and_missing_sensor_are_separate()
    print()
    test_explanation_detail_source_statuses_and_invariance()
    print()
    test_tsho_rolpa_insufficient_explanation()
    print()
    test_real_observed_evidence_is_lifecycle_compatible()
    print()
    test_json_shape_success_and_error()
    print("-" * 40)
    print("Test result: PASS")
