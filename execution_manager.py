"""Synchronous, validity-gated orchestration for one G-ALERT monitoring job."""

from copy import deepcopy

from early_warning_status import EARLY_WARNING_STATUSES, INSUFFICIENT_DATA


STAGE_ORDER = (
    "IMAGERY_ACQUISITION",
    "DATA_QUALITY_MASKING",
    "ACQUISITION_TIMELINE_VALIDATION",
    "OBSERVATION_STORAGE",
    "SEASONAL_BASELINE_COMPARISON",
    "RISK_ASSESSMENT",
    "EARLY_WARNING_STATUS",
)


class MonitoringExecutionManager:
    """Run one synchronous job through existing stage-contract adapters."""

    def __init__(self, stage_handlers):
        missing = [stage for stage in STAGE_ORDER if stage not in stage_handlers]
        if missing:
            raise ValueError(f"Missing stage handlers: {', '.join(missing)}")
        self.stage_handlers = dict(stage_handlers)

    def run(self, initial_context=None):
        """Execute stages sequentially and stop at the first invalid result.

        A handler receives the accumulated context and must return a dictionary
        containing ``ok: True`` and optionally ``context``. It may return
        ``ok: False``, a failure ``status``, and a human-readable ``reason``.
        """
        context = deepcopy(initial_context or {})
        stage_results = []
        completed = []

        for stage in STAGE_ORDER:
            handler = self.stage_handlers[stage]
            try:
                result = handler(context)
            except Exception as exc:
                return self._failure(
                    stage_results,
                    completed,
                    stage,
                    f"Stage raised {type(exc).__name__}: {exc}",
                    context,
                )

            if not isinstance(result, dict):
                return self._failure(
                    stage_results,
                    completed,
                    stage,
                    "Stage returned a non-dictionary result",
                    context,
                )
            stage_record = {
                key: deepcopy(value)
                for key, value in result.items()
                if key != "context"
            }
            stage_record.setdefault("status", "SUCCEEDED" if result.get("ok") else "FAILED")
            stage_results.append({"stage": stage, **stage_record})

            if result.get("ok") is not True:
                return self._failure(
                    stage_results,
                    completed,
                    stage,
                    result.get("reason", "Stage validity requirements were not met"),
                    context,
                )
            if result.get("valid") is False:
                return self._failure(
                    stage_results,
                    completed,
                    stage,
                    result.get("reason", "Stage returned an invalid result"),
                    context,
                )

            context_update = result.get("context") or {}
            if not isinstance(context_update, dict):
                return self._failure(
                    stage_results,
                    completed,
                    stage,
                    "Stage context update must be a dictionary",
                    context,
                )
            context.update(deepcopy(context_update))
            completed.append(stage)

            if stage == "EARLY_WARNING_STATUS":
                system_status = (context.get("early_warning_status") or {}).get("status")
                if system_status not in EARLY_WARNING_STATUSES:
                    return self._failure(
                        stage_results,
                        completed[:-1],
                        stage,
                        "Early-warning stage did not return a recognized system status",
                        context,
                    )

        final_status = (context.get("early_warning_status") or {}).get(
            "status", INSUFFICIENT_DATA
        )
        return {
            "job_status": "SUCCEEDED",
            "stage_order": list(STAGE_ORDER),
            "completed_stages": completed,
            "skipped_stages": [],
            "failed_stage": None,
            "failure_reason": None,
            "system_status": final_status,
            "stages": stage_results,
            "context": context,
        }

    @staticmethod
    def _failure(stage_results, completed, failed_stage, reason, context):
        failed_index = STAGE_ORDER.index(failed_stage)
        return {
            "job_status": "FAILED",
            "stage_order": list(STAGE_ORDER),
            "completed_stages": list(completed),
            "skipped_stages": list(STAGE_ORDER[failed_index + 1:]),
            "failed_stage": failed_stage,
            "failure_reason": str(reason),
            "system_status": INSUFFICIENT_DATA,
            "stages": stage_results,
            "context": deepcopy(context),
        }