"""
verify_masking_task.py - Task-scoped verification for the SCL quality masking change.

Runs (in order):
1. Syntax/compile check of changed files
2. Module import checks
3. Non-GEE unit checks of apply_quality_mask (SKIPPED path) and water-area docstring integrity
4. Offline contract tests: phase1_integrated_test.py, phase2_nepal_test.py, risk_engine_test.py
5. Live GEE end-to-end: run_integrated_monitoring("Tsho_Rolpa_Nepal") with real
   Sentinel-2 -> SCL masking -> NDWI -> water area. Reports ACTUAL results only.
6. API endpoint smoke check (Flask test client, /api/health, /api/regions)

All output is written to masking_verification_report.txt. No results are fabricated:
if GEE fails, the failure is recorded as-is.
"""

import io
import sys
import json
import traceback
from contextlib import redirect_stdout

REPORT_LINES = []


def log(line=""):
    print(line)
    REPORT_LINES.append(str(line))


def section(title):
    log("")
    log("=" * 70)
    log(title)
    log("=" * 70)


def run_step(name, fn):
    section(f"STEP: {name}")
    try:
        result = fn()
        log(f"[RESULT] {name}: {result if result is not None else 'OK'}")
        return result
    except Exception as exc:
        log(f"[FAILED] {name}: {exc}")
        log(traceback.format_exc())
        return None


def step_compile():
    import py_compile
    for f in ["main.py", "app.py", "satellite/ndwi_analysis.py", "satellite/gee_pipeline.py"]:
        py_compile.compile(f, doraise=True)
        log(f"  compile OK: {f}")
    return "all files compile"


def step_imports():
    from satellite.ndwi_analysis import NDWIAnalyzer, SCL_CONTAMINATION_CLASSES
    log(f"  SCL_CONTAMINATION_CLASSES = {SCL_CONTAMINATION_CLASSES}")
    assert SCL_CONTAMINATION_CLASSES == {3: "cloud_shadow", 8: "cloud_medium_probability",
                                         9: "cloud_high_probability", 10: "thin_cirrus", 11: "snow_ice"}
    import main  # noqa
    import app  # noqa
    log("  main.py and app.py import cleanly")
    return "imports OK"


def step_unit_masking():
    analyzer = NDWIAnalyzer()
    # Non-EE input -> must return image unchanged with status SKIPPED (never fabricated)
    dummy = {"not": "an ee image"}
    masked, info = analyzer.apply_quality_mask(dummy)
    assert masked is dummy, "non-EE input must be returned unchanged"
    assert info["status"] == "SKIPPED", info
    log(f"  non-EE input: status={info['status']}, reason={info.get('reason')}")
    return "SKIPPED path behaves honestly"


def step_offline_tests():
    results = {}
    for script in ["phase1_integrated_test.py", "phase2_nepal_test.py", "risk_engine_test.py"]:
        buf = io.StringIO()
        code = open(script, encoding="utf-8").read()
        g = {"__name__": "__main__", "__file__": script}
        with redirect_stdout(buf):
            try:
                exec(compile(code, script, "exec"), g)
                results[script] = "PASS"
                tail = buf.getvalue().strip().splitlines()[-3:]
                for line in tail:
                    log(f"    {script}: {line}")
            except SystemExit as e:
                results[script] = f"EXIT({e.code})"
            except Exception:
                results[script] = "FAIL"
                log(f"    {script} traceback:")
                log(traceback.format_exc())
    log(f"  offline test results: {results}")
    return results


def step_live_gee():
    import main as m
    buf = io.StringIO()
    with redirect_stdout(buf):
        observation = m.run_integrated_monitoring("Tsho_Rolpa_Nepal")
    log("  console output from run_integrated_monitoring (verbatim):")
    for line in buf.getvalue().splitlines():
        log(f"    | {line}")
    status = observation.get("status")
    log(f"  observation.status = {status}")
    if status == "SUCCESS":
        sat = observation["satellite"]
        qm = sat.get("quality_masking", {})
        log(f"  image_id           = {sat.get('image_id')}")
        log(f"  acquisition_time   = {sat.get('acquisition_time')}")
        log(f"  cloud_cover_pct    = {sat.get('cloud_cover_percent')}")
        log(f"  ndwi_value (mean)  = {sat.get('ndwi_value')}")
        log(f"  ndwi_threshold     = {sat.get('ndwi_threshold')}")
        log(f"  water_area         = {sat.get('water_area')}")
        log(f"  quality_masking    = {json.dumps(qm, indent=2)}")
        log(f"  baseline status    = {sat.get('baseline', {}).get('status')}")
        log(f"  baseline qm status = {sat.get('baseline', {}).get('quality_masking', {}).get('status')}")
        log(f"  data_quality       = {json.dumps(sat.get('data_quality'), indent=2)}")
        log(f"  risk_level         = {observation['risk']['risk_level']} (score={observation['risk']['risk_score']})")
        return {"status": status, "quality_masking": qm.get("status"),
                "valid_pixel_fraction": qm.get("valid_pixel_fraction"),
                "water_area_sqkm": (sat.get("water_area") or {}).get("area_sqkm")}
    else:
        # Honest failure/fallback reporting — no fabricated success
        log(f"  reason = {observation.get('reason')}")
        log(f"  search metadata = {json.dumps(observation.get('image_search_metadata', {}), indent=2)}")
        return {"status": status, "reason": observation.get("reason")}


def step_api_check():
    from app import app as flask_app
    client = flask_app.test_client()
    for path in ["/api/health", "/api/regions", "/api/regions/Tsho_Rolpa_Nepal"]:
        resp = client.get(path)
        body = resp.get_json()
        log(f"  GET {path} -> HTTP {resp.status_code}, status={body.get('status') if isinstance(body, dict) else 'n/a'}")
    # POST risk-engine demo (offline logic)
    resp = client.post("/api/demo/risk-engine", json={"satellite_signal": 0.7, "ai_signal": 0.0, "sensor_signal": 0.0})
    log(f"  POST /api/demo/risk-engine -> HTTP {resp.status_code}, level={resp.get_json().get('assessment', {}).get('risk_level')}")
    return "API smoke checks done"


def main():
    log("G-ALERT SCL MASKING TASK — VERIFICATION REPORT")
    log("(all results below are actual execution results; nothing is fabricated)")
    run_step("1. Compile check", step_compile)
    run_step("2. Import + SCL constant check", step_imports)
    run_step("3. apply_quality_mask unit check (non-EE path)", step_unit_masking)
    run_step("4. Offline contract tests", step_offline_tests)
    run_step("5. LIVE GEE end-to-end (real Sentinel-2)", step_live_gee)
    run_step("6. API endpoint smoke check", step_api_check)
    section("END OF REPORT")

    with open("masking_verification_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(REPORT_LINES))
    print("\nReport written to masking_verification_report.txt")


if __name__ == "__main__":
    main()