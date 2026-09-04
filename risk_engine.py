"""
risk_engine.py

Central risk assessment engine for G-ALERT.
Combines satellite, AI, and sensor signals into unified risk assessment.

Output levels:
- SAFE (0.0 - 0.3)
- WARNING (0.3 - 0.6)
- HIGH_RISK (0.6 - 0.85)
- CRITICAL (0.85 - 1.0)

IMPORTANT DISCLAIMER:
- Risk weights (satellite: 0.4, AI: 0.3, sensor: 0.3) are PROTOTYPE values
- Risk thresholds (SAFE: 0.3, WARNING: 0.6, HIGH_RISK: 0.85) are PROTOTYPE values
- These are NOT scientifically validated for GLOF prediction
- No published GLOF research supports these specific numerical values
- Risk calculation methodology is sound, but numerical parameters require
  scientific validation for operational use
- This system is suitable for hackathon demonstration but NOT for operational
  disaster prediction or public warning without scientific validation
"""

import json
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List


class RiskLevel(Enum):
    """Risk level classifications."""
    SAFE = "SAFE"
    WARNING = "WARNING"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"


class RiskEngine:
    """Central risk assessment engine."""
    
    def __init__(self, weights=None):
        """
        Initialize risk engine.
        
        Args:
            weights: dict with signal weights
                    {
                        "satellite": 0.4,
                        "ai": 0.3,
                        "sensor": 0.3
                    }
                    Sum should equal 1.0
        """
        
        # Default equal weighting
        self.weights = weights or {
            "satellite": 0.4,
            "ai": 0.3,
            "sensor": 0.3
        }
        
        # Normalize weights
        total = sum(self.weights.values())
        if total != 1.0:
            for key in self.weights:
                self.weights[key] /= total
        
        # Configuration thresholds (PROTOTYPE VALUES)
        self.thresholds = {
            "SAFE": 0.3,
            "WARNING": 0.6,
            "HIGH_RISK": 0.85
        }
        
        self.last_assessment = None
        self.history = []
    
    def assess_risk(self, satellite_signal=None, ai_signal=None, sensor_signal=None, region=None):
        """
        Assess overall risk from available signals.
        
        Args:
            satellite_signal: float (0-1) from satellite observations
            ai_signal: float (0-1) from AI detections
            sensor_signal: float (0-1) from sensors
            region: optional region identifier for event history
            
        Returns:
            dict with risk assessment
        """
        
        # Handle None values (data not available)
        satellite_signal = satellite_signal or 0.0
        ai_signal = ai_signal or 0.0
        sensor_signal = sensor_signal or 0.0
        
        # Clamp to 0-1 range
        satellite_signal = max(0, min(1, satellite_signal))
        ai_signal = max(0, min(1, ai_signal))
        sensor_signal = max(0, min(1, sensor_signal))
        
        # Calculate weighted risk score
        risk_score = (
            self.weights["satellite"] * satellite_signal +
            self.weights["ai"] * ai_signal +
            self.weights["sensor"] * sensor_signal
        )
        
        # Determine risk level
        if risk_score < self.thresholds["SAFE"]:
            risk_level = RiskLevel.SAFE
        elif risk_score < self.thresholds["WARNING"]:
            risk_level = RiskLevel.WARNING
        elif risk_score < self.thresholds["HIGH_RISK"]:
            risk_level = RiskLevel.HIGH_RISK
        else:
            risk_level = RiskLevel.CRITICAL
        
        # Generate explanation
        explanation = self._generate_explanation(
            satellite_signal, ai_signal, sensor_signal, risk_score
        )
        
        if risk_level == RiskLevel.SAFE:
            action = "Continue monitoring"
        elif risk_level == RiskLevel.WARNING:
            action = "Increase monitoring and review observations"
        elif risk_level == RiskLevel.HIGH_RISK:
            action = "Review downstream exposure and prepare warning"
        else:
            action = "Trigger emergency-warning workflow"

        assessment = {
            "timestamp": datetime.now().isoformat(),
            "risk_score": round(risk_score, 4),
            "risk_level": risk_level.value,
            "action": action,
            "explanation": explanation,
            "signals": {
                "satellite": round(satellite_signal, 4),
                "ai": round(ai_signal, 4),
                "sensor": round(sensor_signal, 4)
            },
            "weights": self.weights,
            "thresholds": self.thresholds
        }

        history_entry = {
            "timestamp": assessment["timestamp"],
            "region": region,
            "risk_score": assessment["risk_score"],
            "risk_level": assessment["risk_level"],
            "satellite_signal": round(satellite_signal, 4),
            "ai_signal": round(ai_signal, 4),
            "sensor_signal": round(sensor_signal, 4),
            "explanation": assessment["explanation"],
            "action": assessment["action"]
        }
        self.history.append(history_entry)
        
        self.last_assessment = assessment
        return assessment
    
    def _generate_explanation(self, sat, ai, sensor, score):
        """Generate human-readable explanation of risk level."""
        
        reasons = []
        
        # Analyze satellite signal
        if sat > 0.6:
            reasons.append(f"Satellite observation shows significant water/lake changes (signal: {sat:.2f})")
        elif sat > 0.3:
            reasons.append(f"Satellite observation shows moderate changes (signal: {sat:.2f})")
        
        # Analyze AI signal
        if ai > 0.6:
            reasons.append(f"AI detects anomalies (signal: {ai:.2f})")
        elif ai > 0.3:
            reasons.append(f"AI detects minor anomalies (signal: {ai:.2f})")
        
        # Analyze sensor signal
        if sensor > 0.6:
            reasons.append(f"Sensors indicate abnormal conditions (signal: {sensor:.2f})")
        elif sensor > 0.3:
            reasons.append(f"Sensors show minor deviations (signal: {sensor:.2f})")
        
        # Overall assessment
        if score < 0.3:
            reasons.append("All indicators normal. No immediate threat detected.")
        elif score < 0.6:
            reasons.append("Caution advised. Monitor conditions closely.")
        elif score < 0.85:
            reasons.append("High risk conditions detected. Increased vigilance required.")
        else:
            reasons.append("CRITICAL CONDITIONS. Immediate action required.")
        
        return " | ".join(reasons)
    
    def calculate_satellite_signal(self, observations):
        """
        Calculate satellite signal from observations.
        
        Args:
            observations: dict with:
                - current_area_sqkm
                - previous_area_sqkm (optional)
                - ndwi_value (optional)
                - cloud_cover (optional)
                - data_quality (optional dict with confidence 0-1)
                
        Returns:
            float signal value (0-1)
        """
        
        signal = 0.0
        
        # NDWI-based signal (higher NDWI = more water)
        ndwi = observations.get("ndwi_value", 0)
        if ndwi > 0.5:
            signal += 0.4  # Strong water signal
        elif ndwi > 0.3:
            signal += 0.2  # Moderate water signal
        
        # Area change signal
        current = observations.get("current_area_sqkm", 0)
        previous = observations.get("previous_area_sqkm", current)
        
        if previous > 0:
            percent_change = ((current - previous) / previous) * 100
            
            if percent_change > 20:
                signal += 0.5  # Significant increase
            elif percent_change > 10:
                signal += 0.3  # Moderate increase
            elif percent_change < -10:
                signal += 0.1  # Decrease (less concerning)
        
        # Cloud cover penalty (less confidence)
        cloud_cover = observations.get("cloud_cover_percent", 0)
        if cloud_cover > 50:
            signal *= 0.8  # Reduce confidence due to clouds

        data_quality = observations.get("data_quality")
        if data_quality is not None:
            confidence = data_quality.get("confidence", 0.0)
            confidence = max(0.0, min(1.0, confidence))
            signal *= confidence
        
        return min(signal, 1.0)
    
    def calculate_ai_signal(self, detections):
        """
        Calculate AI signal from YOLOv8 detections.
        
        Args:
            detections: list of Detection objects or anomaly score
            
        Returns:
            float signal value (0-1)
        """
        
        if isinstance(detections, (int, float)):
            return min(detections, 1.0)
        
        if not detections:
            return 0.0
        
        # If list of detections
        if isinstance(detections, list):
            if len(detections) == 0:
                return 0.0
            
            # Average confidence of detections
            avg_confidence = sum(d.confidence for d in detections) / len(detections)
            
            # More detections = higher signal
            detection_factor = min(len(detections) / 5, 1.0)  # Max 5 detections
            
            signal = (avg_confidence * 0.7) + (detection_factor * 0.3)
            return signal
        
        return 0.0
    
    def calculate_sensor_signal(self, sensor_readings):
        """
        Calculate sensor signal from virtual sensors.
        
        Args:
            sensor_readings: dict with sensor values:
                - vibration_cmps (cm/s²)
                - water_level_cm
                - rainfall_mmph (optional dict with value/anomaly_factor)
                - temperature_c (optional)
                
        Returns:
            float signal value (0-1)
        """
        
        signal = 0.0
        
        # Vibration signal
        # Normal: ~2 cm/s², Anomaly: >10 cm/s², Critical: >30 cm/s²
        vibration = sensor_readings.get("vibration_cmps", 0)
        
        if vibration > 30:
            signal += 0.5  # Critical vibration
        elif vibration > 10:
            signal += 0.3  # Abnormal vibration
        elif vibration > 5:
            signal += 0.1  # Elevated vibration
        
        # Water level signal
        # Normal: 150cm, Alert: >170cm, Critical: >250cm
        water_level = sensor_readings.get("water_level_cm", 0)
        normal_level = 150
        
        if water_level > 250:
            signal += 0.5  # Critical level
        elif water_level > 200:
            signal += 0.3  # High level
        elif water_level > 170:
            signal += 0.1  # Elevated level

        # Prototype-only rainfall support: use the sensor anomaly factor as a small
        # additional contribution without changing the public RiskEngine API or the
        # existing vibration/water-level logic.
        rainfall = sensor_readings.get("rainfall_mmph")
        if isinstance(rainfall, dict):
            rainfall_anomaly = rainfall.get("anomaly_factor", 0.0)
            rainfall_anomaly = max(0.0, min(1.0, float(rainfall_anomaly)))
            signal += rainfall_anomaly * 0.1
        
        return min(signal, 1.0)
    
    def update_weights(self, weights):
        """
        Update signal weights.
        
        Args:
            weights: dict with new weights
        """
        
        self.weights = weights.copy()
        
        # Normalize
        total = sum(self.weights.values())
        for key in self.weights:
            self.weights[key] /= total
        
        print(f"✓ Risk engine weights updated: {self.weights}")
    
    def update_thresholds(self, thresholds):
        """
        Update risk thresholds.
        
        Args:
            thresholds: dict with SAFE, WARNING, HIGH_RISK values
        """
        
        self.thresholds = thresholds
        print(f"✓ Risk engine thresholds updated: {self.thresholds}")


class RiskAssessment:
    """Encapsulates a complete risk assessment result."""
    
    def __init__(self, timestamp, risk_level, risk_score, 
                 satellite_signal=None, ai_signal=None, sensor_signal=None,
                 explanation="", region=""):
        """
        Create risk assessment.
        
        Args:
            timestamp: Assessment timestamp
            risk_level: RiskLevel enum
            risk_score: Overall risk score (0-1)
            satellite_signal: Satellite component (0-1)
            ai_signal: AI component (0-1)
            sensor_signal: Sensor component (0-1)
            explanation: Human-readable explanation
            region: Region assessed
        """
        
        self.timestamp = timestamp
        self.risk_level = risk_level
        self.risk_score = risk_score
        self.satellite_signal = satellite_signal
        self.ai_signal = ai_signal
        self.sensor_signal = sensor_signal
        self.explanation = explanation
        self.region = region
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "region": self.region,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, RiskLevel) else self.risk_level,
            "risk_score": round(self.risk_score, 4),
            "signals": {
                "satellite": round(self.satellite_signal, 4) if self.satellite_signal else None,
                "ai": round(self.ai_signal, 4) if self.ai_signal else None,
                "sensor": round(self.sensor_signal, 4) if self.sensor_signal else None
            },
            "explanation": self.explanation
        }
    
    def to_json_string(self):
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
