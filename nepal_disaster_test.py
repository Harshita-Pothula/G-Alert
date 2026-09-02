from simulation.nepal_disaster import NepalDisasterScenario

scenario = NepalDisasterScenario()

expected = ["NORMAL", "ALERT", "HIGH_ALERT", "CRITICAL", "INCIDENT"]
actual = []

print("G-ALERT Nepal Disaster Simulation Test")
print("All values are SIMULATED.")
print("-" * 40)

while True:
    event = scenario.get_next_event()
    if event is None:
        break

    phase = event["phase"].value
    actual.append(phase)

    print(
        f"{phase}: vibration={event['vibration_cmps']} | "
        f"water={event['water_level_cm']} | "
        f"risk={event['risk_level']} ({event['risk_score']})"
    )

print("-" * 40)
print("Test result:", "PASS" if actual == expected else "FAIL")