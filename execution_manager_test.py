"""Focused integration tests for synchronous monitoring execution."""

from execution_manager import MonitoringExecutionManager, STAGE_ORDER


def _handlers(calls, failure=None):
    handlers = {}
    for stage in STAGE_ORDER:
        def handler(*_args, stage=stage):
            _ = _args
            calls.append(stage)
            if stage == failure:
                return {
                    "ok": False,
                    "status": "STALE_IMAGERY" if stage == "ACQUISITION_TIMELINE_VALIDATION" else "INVALID",
                    "reason": f"{stage} validity gate failed",
                }
            update = {}
            if stage == "EARLY_WARNING_STATUS":
                update["early_warning_status"] = {
                    "status": "WATCH",
                    "reasons": ["verified developing condition"],
                }
            return {"ok": True, "status": "VALID", "context": update}
        handlers[stage] = handler
    return handlers


def test_every_stage_runs_in_exact_order_and_reaches_final_status():
    calls = []
    result = MonitoringExecutionManager(_handlers(calls)).run()
    assert calls == list(STAGE_ORDER)
    assert result["job_status"] == "SUCCEEDED"
    assert result["system_status"] == "WATCH"
    assert result["skipped_stages"] == []


def test_each_stage_failure_skips_all_downstream_stages():
    for failed_stage in STAGE_ORDER:
        calls = []
        result = MonitoringExecutionManager(_handlers(calls, failed_stage)).run()
        failed_index = STAGE_ORDER.index(failed_stage)
        assert result["job_status"] == "FAILED"
        assert result["failed_stage"] == failed_stage
        assert result["system_status"] == "INSUFFICIENT_DATA"
        assert calls == list(STAGE_ORDER[: failed_index + 1])
        assert result["skipped_stages"] == list(STAGE_ORDER[failed_index + 1:])
        assert failed_stage in result["failure_reason"]


def test_stale_invalid_and_insufficient_results_are_not_passed_forward():
    for failure in (
        "DATA_QUALITY_MASKING",
        "ACQUISITION_TIMELINE_VALIDATION",
        "SEASONAL_BASELINE_COMPARISON",
    ):
        calls = []
        result = MonitoringExecutionManager(_handlers(calls, failure)).run(
            {"observation": {"status": "SUCCESS"}}
        )
        assert result["job_status"] == "FAILED"
        assert result["system_status"] == "INSUFFICIENT_DATA"
        assert result["context"]["observation"]["status"] == "SUCCESS"
        assert result["skipped_stages"]


def test_stage_exceptions_produce_structured_failure():
    calls = []
    handlers = _handlers(calls)

    def broken_handler(*_args):
        _ = _args
        calls.append("DATA_QUALITY_MASKING")
        raise RuntimeError("SCL service unavailable")

    handlers["DATA_QUALITY_MASKING"] = broken_handler
    result = MonitoringExecutionManager(handlers).run()
    assert result["job_status"] == "FAILED"
    assert result["failed_stage"] == "DATA_QUALITY_MASKING"
    assert "SCL service unavailable" in result["failure_reason"]
    assert result["skipped_stages"] == list(STAGE_ORDER[2:])


if __name__ == "__main__":
    test_every_stage_runs_in_exact_order_and_reaches_final_status()
    test_each_stage_failure_skips_all_downstream_stages()
    test_stale_invalid_and_insufficient_results_are_not_passed_forward()
    test_stage_exceptions_produce_structured_failure()
    print("Execution manager tests: PASS")