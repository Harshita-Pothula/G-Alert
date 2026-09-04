"""
simulation/sensor_simulator.py

Virtual sensor simulator for Wokwi Arduino/ESP32.
Generates realistic sensor readings (vibration, water level, etc).
All data is SIMULATED, not real historical measurements.
"""

import random
from datetime import datetime, timedelta
import json
from enum import Enum


class SensorType(Enum):
    """Available sensor types."""
    VIBRATION = "vibration"
    WATER_LEVEL = "water_level"
    RAINFALL = "rainfall"
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    PRESSURE = "pressure"


class VirtualSensor:
    """Base class for virtual sensors."""
    
    def __init__(self, sensor_id, sensor_type, location, baseline_value=0, noise_level=1):
        """
        Initialize virtual sensor.
        
        Args:
            sensor_id: Unique sensor identifier
            sensor_type: SensorType enum value
            location: Physical location/region
            baseline_value: Normal/baseline sensor value
            noise_level: Random noise magnitude
        """
        
        self.sensor_id = sensor_id
        self.sensor_type = sensor_type
        self.location = location
        self.baseline_value = baseline_value
        self.noise_level = noise_level
        self.last_reading = None
        self.readings_history = []
    
    def read(self, anomaly_factor=0.0):
        """
        Generate sensor reading.
        
        Args:
            anomaly_factor: 0-1 value indicating anomaly magnitude
                           0.0 = normal, 1.0 = critical anomaly
        
        Returns:
            float sensor reading value
        """
        
        # Base reading with noise
        noise = random.gauss(0, self.noise_level)
        reading = self.baseline_value + noise
        
        # Add anomaly if factor > 0
        if anomaly_factor > 0:
            anomaly = self.baseline_value * anomaly_factor * random.uniform(0.8, 1.2)
            reading += anomaly
        
        # Clamp to valid range
        reading = max(0, reading)
        
        self.last_reading = {
            "value": round(reading, 2),
            "timestamp": datetime.now(),
            "anomaly_factor": anomaly_factor
        }
        
        self.readings_history.append(self.last_reading)
        return reading
    
    def to_dict(self):
        """Convert last reading to dict."""
        if self.last_reading is None:
            return {}
        
        return {
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type.value,
            "location": self.location,
            "value": self.last_reading["value"],
            "timestamp": self.last_reading["timestamp"].isoformat(),
            "anomaly_factor": self.last_reading["anomaly_factor"],
            "status": "ACTIVE",
            "source": "virtual_sensor_simulation",
            "simulated": True
        }


class VibrationSensor(VirtualSensor):
    """Virtual vibration sensor (accelerometer-like)."""
    
    def __init__(self, sensor_id, location):
        """
        Initialize vibration sensor.
        
        Args:
            sensor_id: Sensor identifier
            location: Installation location
        """
        # Baseline: ~2 cm/s² (normal ground vibration)
        # Units: cm/s²
        super().__init__(
            sensor_id=sensor_id,
            sensor_type=SensorType.VIBRATION,
            location=location,
            baseline_value=2.0,  # Normal background vibration
            noise_level=0.5
        )


class WaterLevelSensor(VirtualSensor):
    """Virtual water level sensor (ultrasonic distance)."""
    
    def __init__(self, sensor_id, location, normal_level=150):
        """
        Initialize water level sensor.
        
        Args:
            sensor_id: Sensor identifier
            location: Installation location
            normal_level: Normal water level in cm
        """
        # Units: cm from sensor
        super().__init__(
            sensor_id=sensor_id,
            sensor_type=SensorType.WATER_LEVEL,
            location=location,
            baseline_value=normal_level,  # Normal level
            noise_level=2.0
        )
        self.normal_level = normal_level


class RainfallSensor(VirtualSensor):
    """Virtual rainfall sensor (simulated mm/hour)."""

    def __init__(self, sensor_id, location, normal_rainfall=20.0):
        """
        Initialize rainfall sensor.

        Args:
            sensor_id: Sensor identifier
            location: Installation location
            normal_rainfall: Normal rainfall intensity in mm/hour
        """
        super().__init__(
            sensor_id=sensor_id,
            sensor_type=SensorType.RAINFALL,
            location=location,
            baseline_value=normal_rainfall,
            noise_level=3.0
        )
        self.normal_rainfall = normal_rainfall


class SensorNetwork:
    """Network of multiple virtual sensors."""
    
    def __init__(self, location):
        """
        Initialize sensor network.
        
        Args:
            location: Location/region name (e.g., "Nepal_Pokhara")
        """
        
        self.location = location
        self.sensors = {}
        self.readings_timestamp = None
    
    def add_sensor(self, sensor):
        """Add sensor to network."""
        self.sensors[sensor.sensor_id] = sensor
        print(f"✓ Added sensor: {sensor.sensor_id} ({sensor.sensor_type.value})")
    
    def add_vibration_sensor(self, sensor_id):
        """Convenience method to add vibration sensor."""
        sensor = VibrationSensor(sensor_id, self.location)
        self.add_sensor(sensor)
        return sensor
    
    def add_water_level_sensor(self, sensor_id, normal_level=150):
        """Convenience method to add water level sensor."""
        sensor = WaterLevelSensor(sensor_id, self.location, normal_level)
        self.add_sensor(sensor)
        return sensor

    def add_rainfall_sensor(self, sensor_id, normal_rainfall=20.0):
        """Convenience method to add rainfall sensor."""
        sensor = RainfallSensor(sensor_id, self.location, normal_rainfall)
        self.add_sensor(sensor)
        return sensor
    
    def read_all_sensors(self, anomaly_factors=None):
        """
        Read all sensors at once.
        
        Args:
            anomaly_factors: dict with {sensor_id: anomaly_factor}
                            or None for all normal readings
        
        Returns:
            dict with all sensor readings
        """
        
        anomaly_factors = anomaly_factors or {}
        readings = {}
        
        for sensor_id, sensor in self.sensors.items():
            anomaly = anomaly_factors.get(sensor_id, 0.0)
            sensor.read(anomaly_factor=anomaly)
            readings[sensor_id] = sensor.to_dict()
        
        self.readings_timestamp = datetime.now()
        
        return {
            "location": self.location,
            "timestamp": self.readings_timestamp.isoformat(),
            "sensors": readings
        }
    
    def get_all_readings_json(self):
        """Get all sensor readings as JSON string."""
        
        readings = {
            "location": self.location,
            "timestamp": self.readings_timestamp.isoformat() if self.readings_timestamp else None,
            "sensor_count": len(self.sensors),
            "sensors": {
                sensor_id: sensor.to_dict()
                for sensor_id, sensor in self.sensors.items()
            }
        }
        
        return json.dumps(readings, indent=2)


class SensorObservation:
    """Encapsulates sensor readings at a point in time."""
    
    def __init__(self, location, timestamp, sensor_readings):
        """
        Create sensor observation record.
        
        Args:
            location: Location/region
            timestamp: Observation timestamp
            sensor_readings: dict with sensor readings
        """
        
        self.location = location
        self.timestamp = timestamp or datetime.now()
        self.sensor_readings = sensor_readings
        self.source = "virtual_sensor"  # Not real measurements
    
    def get_vibration_reading(self):
        """Get vibration value from readings."""
        for reading in self.sensor_readings.values():
            if reading.get("sensor_type") == "vibration":
                return reading.get("value")
        return None
    
    def get_water_level_reading(self):
        """Get water level value from readings."""
        for reading in self.sensor_readings.values():
            if reading.get("sensor_type") == "water_level":
                return reading.get("value")
        return None
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "location": self.location,
            "timestamp": self.timestamp.isoformat(),
            "sensor_readings": self.sensor_readings,
            "source": self.source,
            "note": "Simulated virtual sensor readings - NOT real measurements"
        }
    
    def to_json_string(self):
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
