from risk_engine import RiskEngine

engine = RiskEngine()

print("G-ALERT Risk Engine Test")
print("-" * 30)

tests = [
    ("SAFE", 0.1, 0.1, 0.1),
    ("WARNING", 0.4, 0.4, 0.4),
    ("HIGH_RISK", 0.8, 0.8, 0.8),
    ("CRITICAL", 1.0, 1.0, 1.0),
]

passed = True

for expected, sat, ai, sensor in tests:
    result = engine.assess_risk(sat, ai, sensor)
    actual = result["risk_level"]
    print(f"{expected}: score={result['risk_score']} | result={actual}")

    if actual != expected:
        passed = False

print("-" * 30)
print("Test result:", "PASS" if passed else "FAIL")

print("\nSatellite data-quality tests")
positive_area_increase = engine.calculate_satellite_signal({
    "current_area_sqkm": 15.0,
    "previous_area_sqkm": 10.0,
    "data_quality": {"confidence": 1.0},
})
if positive_area_increase <= 0:
    raise SystemExit("Positive real area increase must produce a positive satellite signal")

good_quality = engine.calculate_satellite_signal({
    "current_area_sqkm": 15.0,
    "previous_area_sqkm": 10.0,
    "data_quality": {"confidence": 1.0}
})
poor_quality = engine.calculate_satellite_signal({
    "current_area_sqkm": 15.0,
    "previous_area_sqkm": 10.0,
    "data_quality": {"confidence": 0.2}
})
missing_baseline = engine.calculate_satellite_signal({
    "ndwi_value": 0.8,
    "current_area_sqkm": 15.0,
    "data_quality": {"confidence": 0.0}
})

print(f"Good-quality valid area change signal: {good_quality}")
print(f"Poor-quality cloudy observation signal: {poor_quality}")
print(f"Missing-baseline signal: {missing_baseline}")

quality_passed = good_quality == 0.5 and poor_quality == 0.1 and missing_baseline == 0.0
print("Quality test result:", "PASS" if quality_passed else "FAIL")
if not quality_passed:
    raise SystemExit(1)