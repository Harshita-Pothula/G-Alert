"""Small test-only water-level sensor simulation.

Uses the existing WaterLevelSensor and SensorNetwork logic from the project.
Does not modify the production simulator or risk engine.
"""

from simulation.sensor_simulator import SensorNetwork


def main() -> None:
    print("G-ALERT water-level simulation test")
    print("All values are SIMULATED, not real sensor measurements.")

    network = SensorNetwork("Nepal_Himalayas")
    sensor = network.add_water_level_sensor("WL-001", normal_level=150)

    print("\nNormal readings:")
    for i in range(3):
        value = sensor.read(anomaly_factor=0.0)
        reading = sensor.to_dict()
        print(f"  [{i + 1}] SIMULATED water level = {reading['value']} cm | status = NORMAL")
        assert isinstance(reading["value"], (int, float))

    print("\nIncreasing / anomalous readings:")
    for i, anomaly in enumerate([0.15, 0.35, 0.65, 0.9], start=1):
        value = sensor.read(anomaly_factor=anomaly)
        reading = sensor.to_dict()
        if reading["value"] > sensor.normal_level:
            status = "HIGH"
        else:
            status = "NORMAL"
        print(f"  [{i}] SIMULATED water level = {reading['value']} cm | status = {status} | anomaly_factor = {anomaly}")
        assert isinstance(reading["value"], (int, float))

    print("\nTest result: PASS")
    print("The water-level simulator produced valid numeric SIMULATED readings.")


if __name__ == "__main__":
    main()
