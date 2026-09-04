"""
simulation/nepal_disaster.py

Nepal disaster simulation scenario (Aug 26, 2026 flash flood event - SIMULATED).
Demonstrates how the risk engine would respond to escalating disaster conditions.

IMPORTANT: This is a SIMULATED scenario for hackathon demonstration.
It does NOT represent real historical data.
All sensor values and timings are generated to show system capability.
"""

import json
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Any

from risk_engine import RiskEngine


class DisasterPhase(Enum):
    """Phases of disaster progression."""
    NORMAL = "NORMAL"
    ALERT = "ALERT"
    HIGH_ALERT = "HIGH_ALERT"
    CRITICAL = "CRITICAL"
    INCIDENT = "INCIDENT"


class NepalDisasterScenario:
    """
    Simulates Aug 26, 2026 Nepal flash flood scenario.
    
    Sequence:
    1. NORMAL - Baseline conditions
    2. ALERT - Vibration anomaly detected
    3. HIGH_ALERT - Increasing vibration + water level rise
    4. CRITICAL - Rapid changes, high risk indicators
    5. INCIDENT - Peak disaster conditions (GLOF/flood event)
    """
    
    def __init__(self, start_datetime=None):
        """
        Initialize disaster scenario.
        
        Args:
            start_datetime: Scenario start time (default: datetime.now())
        """
        
        self.start_datetime = start_datetime or datetime(2026, 8, 26, 10, 0, 0)
        self.current_phase = DisasterPhase.NORMAL
        self.events = []
        self.current_timestamp = self.start_datetime
        self.event_sequence = self._generate_event_sequence()
        self.current_event_index = 0
        self.risk_engine = RiskEngine()

    def _normalize_sensor_signal(self, event):
        """Convert simulated vibration/water readings to a 0-1 sensor risk signal."""

        vibration = float(event["vibration_cmps"])
        water_level = float(event["water_level_cm"])

        vibration_signal = min(1.0, vibration / 60.0)
        water_signal = min(1.0, max(0.0, (water_level - 120.0) / 200.0))
        sensor_signal = (0.7 * vibration_signal) + (0.3 * water_signal)
        return round(min(1.0, sensor_signal), 4)

    def _assess_event_with_risk_engine(self, event):
        """Pass the event's simulated signals into the shared RiskEngine."""

        satellite_signal = float(self._estimate_ndwi(event))
        ai_signal = float(self._estimate_ai_anomaly(event))
        sensor_signal = self._normalize_sensor_signal(event)

        assessment = self.risk_engine.assess_risk(
            satellite_signal=satellite_signal,
            ai_signal=ai_signal,
            sensor_signal=sensor_signal,
            region="Nepal"
        )

        # Keep scripted event["risk_level"] / event["risk_score"] as placeholders.
        # Displayed classification comes only from this RiskEngine assessment.
        event["risk_assessment"] = assessment
        event["risk_explanation"] = assessment["explanation"]
        event["risk_action"] = assessment["action"]
        if self.risk_engine.history:
            self.risk_engine.history[-1]["simulation_phase"] = event["phase"].value

        return assessment
    
    def _generate_event_sequence(self):
        """Generate the sequence of disaster events."""
        
        events = [
            # Phase 1: NORMAL (hours 0-2)
            {
                "phase": DisasterPhase.NORMAL,
                "hours_from_start": 0,
                "event": "System operational. All readings normal.",
                "vibration_cmps": 2.0,
                "water_level_cm": 150,
                "risk_level": "SAFE",
                "risk_score": 0.1
            },
            
            # Phase 2: ALERT (hours 2-4)
            {
                "phase": DisasterPhase.ALERT,
                "hours_from_start": 2,
                "event": "Vibration anomaly detected. Minor earthquake or rockfall upstream.",
                "vibration_cmps": 8.5,
                "water_level_cm": 152,
                "risk_level": "WARNING",
                "risk_score": 0.35
            },
            
            # Phase 3: HIGH_ALERT (hours 4-6)
            {
                "phase": DisasterPhase.HIGH_ALERT,
                "hours_from_start": 4,
                "event": "Increasing vibration intensity and water level. Simulated hazard indicators are rising.",
                "vibration_cmps": 18.5,
                "water_level_cm": 165,
                "risk_level": "WARNING",
                "risk_score": 0.55
            },
            
            # Phase 4: CRITICAL (hours 6-8)
            {
                "phase": DisasterPhase.CRITICAL,
                "hours_from_start": 6,
                "event": "CRITICAL: Strong vibrations and rapid water level rise. Simulated critical escalation requiring emergency-warning workflow.",
                "vibration_cmps": 35.0,
                "water_level_cm": 195,
                "risk_level": "HIGH_RISK",
                "risk_score": 0.75
            },
            
            # Phase 5: INCIDENT (hours 8+)
            {
                "phase": DisasterPhase.INCIDENT,
                "hours_from_start": 8,
                "event": "INCIDENT: Simulated extreme conditions for emergency-response demonstration.",
                "vibration_cmps": 55.0,
                "water_level_cm": 280,
                "risk_level": "CRITICAL",
                "risk_score": 0.95
            }
        ]
        
        return events
    
    def get_next_event(self):
        """
        Get next event in disaster sequence.
        
        Returns:
            dict with event data or None if scenario complete
        """
        
        if self.current_event_index >= len(self.event_sequence):
            return None
        
        event = self.event_sequence[self.current_event_index]
        self.current_timestamp = self.start_datetime + timedelta(hours=event["hours_from_start"])
        self.current_phase = event["phase"]
        
        # Add timestamp to event
        event["timestamp"] = self.current_timestamp.isoformat()
        
        self.current_event_index += 1
        return event
    
    def get_event_at_phase(self, phase):
        """Get event for specific phase."""
        
        for event in self.event_sequence:
            if event["phase"] == phase:
                event["timestamp"] = self.start_datetime + timedelta(hours=event["hours_from_start"])
                return event
        
        return None
    
    def generate_telemetry(self, event=None):
        """
        Generate structured telemetry for an event.
        
        Args:
            event: Event dict (or None to use current event)
            
        Returns:
            Structured telemetry dict
        """
        
        if event is None:
            event = self.get_next_event()
        
        if event is None:
            return None

        assessment = self._assess_event_with_risk_engine(event)
        
        telemetry = {
            "scenario": "Nepal_Aug26_2026_FlashFlood",
            "event_timestamp": event["timestamp"],
            "phase": event["phase"].value,
            "event_description": event["event"],
            
            # Sensor readings (SIMULATED)
            "sensors": {
                "vibration_cmps": event["vibration_cmps"],
                "water_level_cm": event["water_level_cm"],
                "note": "Simulated sensor data - NOT real measurements",
                "simulated": True,
                "status": "simulated"
            },
            
            # Risk assessment
            "risk_level": assessment["risk_level"],
            "risk_score": assessment["risk_score"],
            "risk_explanation": assessment["explanation"],
            "risk_action": assessment["action"],
            "engine_assessment": assessment,
            
            # Satellite observation (if available)
            "satellite_observation": {
                "lake_area_sqkm": self._estimate_lake_area(event),
                "ndwi_value": self._estimate_ndwi(event),
                "simulated": True,
                "status": "simulated"
            },
            
            # AI detection (if available)
            "ai_detection": {
                "anomaly_score": self._estimate_ai_anomaly(event),
                "simulated": True,
                "status": "simulated"
            },
            
            # Source
            "source": "simulation",
            "warning": "All data is SIMULATED for hackathon demonstration purposes",
            "simulated": True
        }
        
        return telemetry
    
    def _estimate_lake_area(self, event):
        """Estimate lake area based on phase."""
        
        phase = event["phase"]
        
        area_map = {
            DisasterPhase.NORMAL: 25.5,
            DisasterPhase.ALERT: 26.0,
            DisasterPhase.HIGH_ALERT: 28.5,
            DisasterPhase.CRITICAL: 32.0,
            DisasterPhase.INCIDENT: 38.5
        }
        
        return area_map.get(phase, 25.5)
    
    def _estimate_ndwi(self, event):
        """Estimate NDWI value based on phase."""
        
        phase = event["phase"]
        
        ndwi_map = {
            DisasterPhase.NORMAL: 0.35,
            DisasterPhase.ALERT: 0.40,
            DisasterPhase.HIGH_ALERT: 0.50,
            DisasterPhase.CRITICAL: 0.65,
            DisasterPhase.INCIDENT: 0.80
        }
        
        return ndwi_map.get(phase, 0.35)
    
    def _estimate_ai_anomaly(self, event):
        """Estimate AI anomaly score based on phase."""
        
        phase = event["phase"]
        
        anomaly_map = {
            DisasterPhase.NORMAL: 0.1,
            DisasterPhase.ALERT: 0.3,
            DisasterPhase.HIGH_ALERT: 0.5,
            DisasterPhase.CRITICAL: 0.7,
            DisasterPhase.INCIDENT: 0.9
        }
        
        return anomaly_map.get(phase, 0.1)
    
    def get_all_events_as_json(self):
        """Get entire event sequence as JSON."""
        
        all_telemetry = []
        
        for event in self.event_sequence:
            event_copy = event.copy()
            event_copy["phase"] = event_copy["phase"].value
            event_copy["timestamp"] = (self.start_datetime + timedelta(hours=event["hours_from_start"])).isoformat()
            all_telemetry.append(event_copy)
        
        return json.dumps(all_telemetry, indent=2)
    
    def get_scenario_summary(self):
        """Get summary of entire scenario."""
        
        summary = {
            "scenario_name": "Nepal Aug 26, 2026 Flash Flood Simulation",
            "start_time": self.start_datetime.isoformat(),
            "duration_hours": self.event_sequence[-1]["hours_from_start"],
            "phases": len(self.event_sequence),
            "warning": "This is a SIMULATED scenario for demonstration purposes. All data is generated.",
            "phases_detail": [
                {
                    "phase": event["phase"].value,
                    "hours": event["hours_from_start"],
                    "description": event["event"],
                    "risk_level": event["risk_level"]
                }
                for event in self.event_sequence
            ]
        }
        
        return json.dumps(summary, indent=2)


class SimulationEvent:
    """Encapsulates a simulation event with telemetry."""
    
    def __init__(self, scenario, phase, event_description, sensor_data, risk_data):
        """
        Create simulation event.
        
        Args:
            scenario: Scenario name
            phase: DisasterPhase value
            event_description: Human-readable event description
            sensor_data: dict with sensor readings
            risk_data: dict with risk assessment
        """
        
        self.scenario = scenario
        self.phase = phase
        self.event_description = event_description
        self.sensor_data = sensor_data
        self.risk_data = risk_data
        self.timestamp = datetime.now()
        self.source = "simulation"
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "scenario": self.scenario,
            "timestamp": self.timestamp.isoformat(),
            "phase": self.phase.value if isinstance(self.phase, DisasterPhase) else self.phase,
            "event": self.event_description,
            "sensors": self.sensor_data,
            "risk": self.risk_data,
            "source": self.source
        }
    
    def to_json_string(self):
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
