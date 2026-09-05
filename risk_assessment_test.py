"""Focused tests for the structured, defensive RiskEngine assessment."""

from risk_engine import ASSESSMENT_META_FLAG, RiskEngine


def test_complete_evidence_is_structured():
    assessment = RiskEngine().assess_risk(
        satellite_signal=0.4,
        ai_signal=0.2,
        sensor_signal=0.3,
        evidence={
            "observed_evidence": ["real Sentinel-2 observation", "sensor reading"],
            "derived_indicators": ["temporal baseline comparison"],
        },
    )

    assert assessment["assessment_status"] == "COMPLETE"
    assert assessment["confidence"] == "PROTOTYPE_LIMITED"
    assert assessment["observed_evidence"]
    assert assessment["derived_indicators"]
    assert assessment["unavailable_information"] == []
    assert assessment["meta_flag"] == ASSESSMENT_META_FLAG


def test_missing_evidence_is_not_safe():
    assessment = RiskEngine().assess_risk(
        satellite_signal=0.2,
        ai_signal=None,
        sensor_signal=0.1,
    )

    assert assessment["risk_level"] == "UNKNOWN"
    assert assessment["assessment_status"] == "LIMITED_CONFIDENCE"
    assert assessment["confidence"] == "LIMITED"
    assert assessment["missing_inputs"] == ["ai"]
    assert "ai signal was not supplied" in assessment["unavailable_information"]
    assert "Insufficient" in assessment["action"]


def test_simulated_evidence_is_separate():
    assessment = RiskEngine().assess_risk(
        satellite_signal=0.8,
        ai_signal=0.4,
        sensor_signal=0.7,
        evidence={
            "simulated_signals": ["Nepal scripted sensor and satellite values"],
        },
    )

    assert assessment["assessment_status"] == "SIMULATED_ASSESSMENT"
    assert assessment["confidence"] == "SIMULATED"
    assert assessment["simulated_signals"]
    assert assessment["observed_evidence"] == []


def test_unavailable_or_withheld_evidence_is_reported():
    assessment = RiskEngine().assess_risk(
        satellite_signal=0.3,
        ai_signal=0.0,
        sensor_signal=0.2,
        evidence={
            "unavailable_information": [
                "Tsho Rolpa identity was withheld by the upstream validity gate"
            ],
        },
    )

    assert assessment["risk_level"] == "UNKNOWN"
    assert assessment["assessment_status"] == "LIMITED_CONFIDENCE"
    assert assessment["unavailable_information"]
    assert "withheld" in assessment["explanation"]


def test_all_missing_evidence_is_insufficient():
    assessment = RiskEngine().assess_risk()

    assert assessment["risk_level"] == "UNKNOWN"
    assert assessment["assessment_status"] == "INSUFFICIENT_CONFIDENCE"
    assert assessment["confidence"] == "INSUFFICIENT"
    assert assessment["decision_support_status"] == "INSUFFICIENT_DATA"


if __name__ == "__main__":
    test_complete_evidence_is_structured()
    test_missing_evidence_is_not_safe()
    test_simulated_evidence_is_separate()
    test_unavailable_or_withheld_evidence_is_reported()
    test_all_missing_evidence_is_insufficient()
    print("Risk assessment tests: PASS")