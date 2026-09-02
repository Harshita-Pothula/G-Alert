"""Small test-only vibration sensor simulation.

Uses the existing VibrationSensor and SensorNetwork logic from the project.
Does not modify the production simulator or risk engine.
"""

from simulation.sensor_simulator import SensorNetwork


def main() -> None:
    print("G-ALERT vibration simulation test")
    print("All values are SIMULATED, not real sensor measurements.")

    network = SensorNetwork("Nepal_Himalayas")
    sensor = network.add_vibration_sensor("VB-001")

    print("\nNormal readings:")
    for i in range(3):
        value = sensor.read(anomaly_factor=0.0)
        reading = sensor.to_dict()
        print(f"  [{i + 1}] SIMULATED vibration = {reading['value']} cm/s² | status = NORMAL")
        assert isinstance(reading["value"], (int, float))

    print("\nIncreasing / anomalous readings:")
    for i, anomaly in enumerate([0.25, 0.55, 0.8, 1.1], start=1):
        value = sensor.read(anomaly_factor=anomaly)
        reading = sensor.to_dict()
        if reading["value"] > 2.0:
            status = "HIGH"
        else:
            status = "NORMAL"
        print(f"  [{i}] SIMULATED vibration = {reading['value']} cm/s² | status = {status} | anomaly_factor = {anomaly}")
        assert isinstance(reading["value"], (int, float))

    print("\nTest result: PASS")
    print("The vibration simulator produced valid numeric SIMULATED readings.")


if __name__ == "__main__":
    main()
