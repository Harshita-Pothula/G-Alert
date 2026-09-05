"""System-level early-warning status derived from existing G-ALERT evidence."""

from copy import deepcopy


NORMAL = "NORMAL"
WATCH = "WATCH"
WARNING = "WARNING"
UNCONFIRMED = "UNCONFIRMED"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

EARLY_WARNING_STATUSES = {
    NORMAL,
    WATCH,
    WARNING,
    UNCONFIRMED,
    INSUFFICIENT_DATA,
}


_INSUFFICIENT_OBSERVATION_STATUSES = {
    "ERROR",
    "NO_SUITABLE_IMAGERY",
    "STALE_IMAGERY",
    "SATELLITE_PROCESSING_ERROR",
}
_INSUFFICIENT_SATELLITE_STATUSES = {
    "NOT_AVAILABLE",
    "NO_SUITABLE_IMAGERY",
    "STALE_IMAGERY",
    "MASKING_FAILED",
    "PROCESSING_FAILED",
}
_AMBIGUOUS_IDENTITY_STATUSES = {
    "IDENTITY_AMBIGUOUS",
    "IDENTITY_UNCERTAIN",
    "IDENTITY_NOT_ESTABLISHED",
    "TEMPORAL_IDENTITY_AMBIGUOUS",
    "TEMPORAL_IDENTITY_NOT_ESTABLISHED",
}


def _identity_status(observation, satellite, temporal):
    return (
        (temporal or {}).get("identity_status")
        or (satellite.get("candidate_detection") or {}).get("identity_status")
        or observation.get("identity_status")
    )


def _status_result(status, reasons, observation, risk, evidence_state):
    provenance = deepcopy(observation.get("provenance"))
    risk = risk or {}
    limitations = list((provenance or {}).get("limitations") or [])
    limitations.extend(risk.get("assumptions") or [])
    return {
        "status": status,
        "reasons": reasons,
        "evidence_state": evidence_state,
        "risk_assessment": deepcopy(risk),
        "provenance": provenance,
        "explanation": {
            "risk_explanation": risk.get("explanation"),
            "assessment_reason": reasons,
            "assumptions": deepcopy(risk.get("assumptions") or []),
            "unavailable_information": deepcopy(
                risk.get("unavailable_information") or []
            ),
            "limitations": limitations,
        },
    }


def evaluate_early_warning_status(observation):
    """Derive one system status without creating a second risk model.

    The function consumes an existing integrated observation envelope. It uses
    the risk engine's categorical result and existing validity/identity gates;
    it does not recalculate a numeric risk score.
    """
    if not isinstance(observation, dict):
        return _status_result(
            INSUFFICIENT_DATA,
            ["Observation envelope is missing or invalid"],
            {},
            {},
            {"observation": "INVALID"},
        )

    satellite = observation.get("satellite") or {}
    temporal = observation.get("temporal_evidence") or {}
    decision_support = observation.get("decision_support") or {}
    risk = observation.get("risk") or {}
    identity = _identity_status(observation, satellite, temporal)
    observation_status = observation.get("status")
    satellite_status = satellite.get("status")
    risk_status = risk.get("assessment_status")
    unavailable = risk.get("unavailable_information") or []
    simulated = risk.get("simulated_signals") or []

    evidence_state = {
        "observation_status": observation_status,
        "satellite_status": satellite_status,
        "identity_status": identity,
        "temporal_status": temporal.get("status") or "NOT_PROVIDED",
        "decision_support_status": decision_support.get("status"),
        "risk_assessment_status": risk_status,
        "risk_confidence": risk.get("confidence"),
    }

    insufficient_reasons = []
    if observation.get("validity_status") == "UNAVAILABLE":
        insufficient_reasons.append("Observation validity status is UNAVAILABLE")
    if satellite.get("validity_status") == "UNAVAILABLE":
        insufficient_reasons.append("Satellite validity status is UNAVAILABLE")
    if observation_status in _INSUFFICIENT_OBSERVATION_STATUSES:
        insufficient_reasons.append(
            f"Observation status is {observation_status}"
        )
    if satellite_status in _INSUFFICIENT_SATELLITE_STATUSES:
        insufficient_reasons.append(f"Satellite status is {satellite_status}")
    if not satellite or not satellite_status:
        insufficient_reasons.append("Satellite evidence is missing")
    if satellite.get("quality_masking", {}).get("status") != "APPLIED":
        insufficient_reasons.append("Satellite quality masking was not applied")
    if satellite_status == "SUCCESS" and (
        not satellite.get("image_id")
        or not satellite.get("acquisition_time")
        or not isinstance(satellite.get("data_quality"), dict)
    ):
        insufficient_reasons.append(
            "Satellite identifier, acquisition time, or data quality is missing"
        )
    if decision_support.get("status") in {"UNAVAILABLE", "INSUFFICIENT_DATA"}:
        insufficient_reasons.append(
            f"Decision support status is {decision_support.get('status')}"
        )
    if not risk:
        insufficient_reasons.append("Structured risk assessment is missing")
    if risk_status in {"INSUFFICIENT_CONFIDENCE", "LIMITED_CONFIDENCE"}:
        insufficient_reasons.append(
            f"Risk assessment status is {risk_status}"
        )
    if unavailable:
        insufficient_reasons.append("Risk assessment contains unavailable information")

    if insufficient_reasons:
        return _status_result(
            INSUFFICIENT_DATA,
            insufficient_reasons,
            observation,
            risk,
            evidence_state,
        )

    unconfirmed_reasons = []
    if identity in _AMBIGUOUS_IDENTITY_STATUSES:
        unconfirmed_reasons.append(f"Lake identity status is {identity}")
    if temporal.get("status") == "TEMPORAL_IDENTITY_AMBIGUOUS":
        unconfirmed_reasons.append("Temporal evidence contains competing persistent candidates")
    if observation.get("evidence_conflict") or observation.get("conflicting_evidence"):
        unconfirmed_reasons.append("Evidence is explicitly conflicting")
    if simulated or observation.get("simulated") or observation.get("mode") == "nepal_simulation":
        unconfirmed_reasons.append("Evidence is simulated rather than a verified observation")
    if identity != "IDENTITY_SUPPORTED":
        unconfirmed_reasons.append("Target-lake identity is not explicitly supported")
    if risk_status != "COMPLETE":
        unconfirmed_reasons.append("Risk assessment is not marked complete")

    if unconfirmed_reasons:
        return _status_result(
            UNCONFIRMED,
            unconfirmed_reasons,
            observation,
            risk,
            evidence_state,
        )

    risk_level = risk.get("risk_level")
    if risk_level in {"HIGH_RISK", "CRITICAL"}:
        return _status_result(
            WARNING,
            [f"Verified risk assessment is {risk_level}"],
            observation,
            risk,
            evidence_state,
        )
    if risk_level == "WARNING":
        return _status_result(
            WATCH,
            ["Risk assessment is WARNING but has not reached high-risk level"],
            observation,
            risk,
            evidence_state,
        )
    if risk_level == "SAFE":
        return _status_result(
            NORMAL,
            ["Complete valid evidence supports the SAFE risk assessment"],
            observation,
            risk,
            evidence_state,
        )

    return _status_result(
        INSUFFICIENT_DATA,
        [f"Risk level {risk_level!r} cannot support an early-warning status"],
        observation,
        risk,
        evidence_state,
    )