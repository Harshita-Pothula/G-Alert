"""
ai/yolov8_detector.py

YOLOv8 object detection for glacier/lake monitoring.
Keeps AI functionality independent from rest of system.
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    from ultralytics import YOLO
except ImportError:
    print("WARNING: ultralytics not installed. Run: pip install ultralytics")
    YOLO = None


class YOLOv8Detector:
    """YOLOv8 object detection wrapper for GLOF monitoring."""
    
    def __init__(self, model_name="yolov8n.pt", confidence_threshold=0.5):
        """
        Initialize YOLOv8 detector.
        
        Args:
            model_name: YOLOv8 model variant
                       - yolov8n.pt (nano - fastest)
                       - yolov8s.pt (small)
                       - yolov8m.pt (medium)
                       - yolov8l.pt (large)
                       - yolov8x.pt (xlarge)
            confidence_threshold: Detection confidence threshold (0-1)
        """
        
        if YOLO is None:
            raise RuntimeError("ultralytics not installed")
        
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.last_detections = None
        
        try:
            self.model = YOLO(model_name)
            print(f"✓ YOLOv8 model loaded: {model_name}")
        except Exception as e:
            print(f"✗ Failed to load YOLOv8 model: {e}")
            raise
    
    def detect_objects(self, image_source, custom_classes=None):
        """
        Run inference on image.
        
        Args:
            image_source: Image path, URL, or PIL Image object
            custom_classes: List of class names to filter (optional)
                           If None, returns all detections
        
        Returns:
            List of Detection objects
        """
        
        try:
            # Run inference
            results = self.model.predict(
                image_source,
                conf=self.confidence_threshold,
                verbose=False
            )
            
            detections = []
            
            # Process results
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        detection = Detection(
                            class_id=int(box.cls),
                            class_name=self.model.names[int(box.cls)],
                            confidence=float(box.conf),
                            bbox=box.xyxy[0].tolist(),  # [x1, y1, x2, y2]
                            area_percent=self._calculate_area_percent(box, result.orig_shape),
                            timestamp=datetime.now()
                        )
                        
                        # Filter by custom classes if provided
                        if custom_classes is None or detection.class_name in custom_classes:
                            detections.append(detection)
            
            self.last_detections = detections
            print(f"✓ Detection complete: {len(detections)} objects found")
            return detections
            
        except Exception as e:
            print(f"✗ Detection failed: {e}")
            return []
    
    def detect_glacial_anomalies(self, image_source):
        """
        Specialized detection for glacier/lake anomalies.
        Looks for potential GLOF indicators (crevasses, water, debris).
        
        Args:
            image_source: Image path/URL
            
        Returns:
            List of Detection objects with glacial context
        """
        
        # Classes that might indicate glacier/water anomalies
        glacier_indicators = [
            "water", "lake", "flood", "crack", "crevasse",
            "snow", "ice", "debris", "avalanche", "debris_flow"
        ]
        
        return self.detect_objects(image_source, custom_classes=glacier_indicators)
    
    def filter_detections(self, detections, class_name=None, min_confidence=None):
        """
        Filter detections by class or confidence.
        
        Args:
            detections: List of Detection objects
            class_name: Filter by class name (optional)
            min_confidence: Minimum confidence threshold (optional)
            
        Returns:
            Filtered list of detections
        """
        
        filtered = detections
        
        if class_name:
            filtered = [d for d in filtered if d.class_name == class_name]
        
        if min_confidence:
            filtered = [d for d in filtered if d.confidence >= min_confidence]
        
        return filtered
    
    def _calculate_area_percent(self, box, original_shape):
        """Calculate bounding box area as percentage of image."""
        
        try:
            h, w = original_shape[:2]
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            box_area = (x2 - x1) * (y2 - y1)
            image_area = h * w
            return (box_area / image_area) * 100
        except:
            return 0


class Detection:
    """Represents a single object detection."""
    
    def __init__(self, class_id, class_name, confidence, bbox, 
                 area_percent=0, timestamp=None):
        """
        Initialize detection.
        
        Args:
            class_id: Class ID from YOLO
            class_name: Class name (e.g., "person", "car")
            confidence: Detection confidence (0-1)
            bbox: Bounding box [x1, y1, x2, y2]
            area_percent: Bounding box area as % of image
            timestamp: Detection timestamp
        """
        
        self.class_id = class_id
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox  # [x1, y1, x2, y2]
        self.area_percent = area_percent
        self.timestamp = timestamp or datetime.now()
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
            "bbox": [round(x, 2) for x in self.bbox],
            "area_percent": round(self.area_percent, 2),
            "timestamp": self.timestamp.isoformat()
        }
    
    def to_json_string(self):
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    def __repr__(self):
        return f"Detection(class={self.class_name}, conf={self.confidence:.2f})"


class AIObservation:
    """Encapsulates AI-based observation (YOLOv8 detection)."""
    
    def __init__(self, region, timestamp, detections):
        """
        Create AI observation record.
        
        Args:
            region: Region name
            timestamp: Observation timestamp
            detections: List of Detection objects
        """
        
        self.region = region
        self.timestamp = timestamp or datetime.now()
        self.detections = detections
        self.anomaly_score = self._calculate_anomaly_score()
        self.source = "ai_detection"
    
    def _calculate_anomaly_score(self):
        """
        Calculate overall anomaly score from detections.
        Returns 0-1 where 1 = high anomaly.
        """
        
        if not self.detections:
            return 0.0
        
        # Simple algorithm: average confidence of all detections
        # (Higher confidence detection = higher anomaly potential)
        avg_confidence = sum(d.confidence for d in self.detections) / len(self.detections)
        return min(avg_confidence, 1.0)
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "region": self.region,
            "timestamp": self.timestamp.isoformat(),
            "detection_count": len(self.detections),
            "detections": [d.to_dict() for d in self.detections],
            "anomaly_score": round(self.anomaly_score, 4),
            "source": self.source
        }
    
    def to_json_string(self):
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
