# G-ALERT Backend - Himalayan Glacial Lake Early Warning System

**Hackathon Prototype** | Early Warning System for Glacial Lake Outburst Floods (GLOFs)

---

## 🎯 Project Goal

Demonstrate how satellite data, AI detection, and virtual sensors can combine to detect and warn about Glacial Lake Outburst Flood (GLOF) risks in the Himalayan region.

**Key Demonstration Points:**
1. ✅ Multi-region glacial lake monitoring via satellite
2. ✅ Water/lake change detection using NDWI analysis
3. ✅ AI-based anomaly detection (YOLOv8)
4. ✅ Virtual sensor network simulation (Wokwi Arduino)
5. ✅ Risk scoring and alert generation
6. ✅ Nepal Aug 26, 2026 disaster scenario replay

---

## ⚠️ Important Disclaimer

**THIS IS A PROTOTYPE/DEMO SYSTEM**

- All sensor readings are **SIMULATED**, not real measurements
- All risk thresholds are **DEMO VALUES**, not scientifically validated
- Satellite observations come from Google Earth Engine (real), but processing is demo-level
- The Nepal scenario is a **SIMULATION**, not real historical data
- This system is NOT suitable for actual disaster prediction

---

## 📁 Project Structure

```
G-ALERT-BACKEND/
│
├── satellite/
│   ├── gee_pipeline.py          # Google Earth Engine connection & Sentinel-2 retrieval
│   ├── ndwi_analysis.py         # NDWI calculation & water detection
│   └── region_config.py         # Himalayan monitoring regions configuration
│
├── ai/
│   └── yolov8_detector.py       # YOLOv8 object detection module
│
├── simulation/
│   ├── sensor_simulator.py      # Virtual sensor network (vibration, water level)
│   └── nepal_disaster.py        # Nepal disaster scenario (Aug 26, 2026 simulation)
│
├── risk_engine.py               # Central risk assessment engine
├── main.py                      # Demo script
├── requirements.txt             # Python dependencies
├── .env                         # Configuration (GEE credentials, thresholds)
└── README.md                    # This file
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

**Python Version:** 3.11.9 recommended (3.13 may have compatibility issues)

### 2. Google Earth Engine Setup

#### Option A: Service Account (Recommended for Backend)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Earth Engine API
4. Create a service account JSON key
5. Place the JSON file in your project root
6. Update `.env`:
   ```
   GEE_CREDENTIALS_PATH=./gee-credentials.json
   ```

#### Option B: Interactive Login

Run in Python:
```python
import ee
ee.Initialize()  # Opens browser for authentication
```

### 3. Run Demo

```bash
python main.py
```

This will demonstrate:
- Virtual sensor network
- Nepal disaster scenario
- Risk engine assessment
- Available monitoring regions

---

## 📡 Core Modules

### A. Satellite Pipeline (`satellite/gee_pipeline.py`)

**Purpose:** Connect to Google Earth Engine and retrieve Sentinel-2 imagery

**Key Classes:**
- `GEEAuthenticator` - Handles GEE authentication
- `Sentinel2Pipeline` - Retrieves and processes satellite data

**Example:**
```python
from satellite.gee_pipeline import initialize_gee_pipeline
from satellite.region_config import get_region_bounds

# Initialize
pipeline = initialize_gee_pipeline()

# Get image
region_bounds = get_region_bounds("Khumbu_Nepal")
image = pipeline.get_sentinel2_image(
    region_bounds,
    start_date="2026-01-01",
    end_date="2026-01-31",
    cloud_cover_max=20
)
```

### B. NDWI Analysis (`satellite/ndwi_analysis.py`)

**Purpose:** Detect and quantify water/lakes using spectral analysis

**Formula:** NDWI = (Green - NIR) / (Green + NIR)

**Key Classes:**
- `NDWIAnalyzer` - Calculates NDWI and water masks
- `WaterObservation` - Stores water observation data

**Example:**
```python
from satellite.ndwi_analysis import NDWIAnalyzer

analyzer = NDWIAnalyzer(ndwi_water_threshold=0.3)
ndwi = analyzer.calculate_ndwi(image)
water_mask = analyzer.create_water_mask(ndwi)
area = analyzer.calculate_water_area(water_mask)
```

### C. Region Configuration (`satellite/region_config.py`)

**Purpose:** Define and manage Himalayan monitoring regions

**Available Regions:**
- Khumbu, Nepal (Mt. Everest region)
- Pokhara, Nepal (major population center)
- Ladakh, India (high-altitude lakes)
- Eastern Bhutan
- Central Tibet

### D. YOLOv8 Detector (`ai/yolov8_detector.py`)

**Purpose:** AI-based object detection for anomalies

**Key Classes:**
- `YOLOv8Detector` - Wrapper around YOLO inference
- `Detection` - Single detection result
- `AIObservation` - Collection of detections

**Example:**
```python
from ai.yolov8_detector import YOLOv8Detector

detector = YOLOv8Detector(model_name="yolov8n.pt")
detections = detector.detect_objects("path/to/image.jpg")

for detection in detections:
    print(f"{detection.class_name}: {detection.confidence:.2f}")
```

### E. Sensor Simulator (`simulation/sensor_simulator.py`)

**Purpose:** Generate virtual sensor readings (vibration, water level)

**Key Classes:**
- `VibrationSensor` - Simulates seismic/ground vibration
- `WaterLevelSensor` - Simulates water depth
- `SensorNetwork` - Network of multiple sensors
- `SensorObservation` - Point-in-time sensor readings

**Example:**
```python
from simulation.sensor_simulator import SensorNetwork

network = SensorNetwork("Nepal_Pokhara")
network.add_vibration_sensor("VIB-001")
network.add_water_level_sensor("WATER-001", normal_level=150)

readings = network.read_all_sensors()
```

### F. Nepal Disaster Simulation (`simulation/nepal_disaster.py`)

**Purpose:** Simulate Nepal Aug 26, 2026 flash flood scenario

**Phases:**
1. **NORMAL** - Baseline conditions
2. **ALERT** - Vibration anomaly detected
3. **HIGH_ALERT** - Increasing vibration + water rise
4. **CRITICAL** - Rapid changes, high risk
5. **INCIDENT** - Peak disaster (GLOF/flood)

**Example:**
```python
from simulation.nepal_disaster import NepalDisasterScenario

scenario = NepalDisasterScenario()

for i in range(5):
    event = scenario.get_next_event()
    print(f"Phase: {event['phase'].value}")
    print(f"Risk Level: {event['risk_level']}")
```

### G. Risk Engine (`risk_engine.py`)

**Purpose:** Central assessment combining all signals into risk level

**Risk Levels:**
- `SAFE` (score 0.0 - 0.3)
- `WARNING` (score 0.3 - 0.6)
- `HIGH_RISK` (score 0.6 - 0.85)
- `CRITICAL` (score 0.85 - 1.0)

**Signal Weights (Configurable):**
- Satellite: 40%
- AI: 30%
- Sensor: 30%

**Example:**
```python
from risk_engine import RiskEngine

engine = RiskEngine()

assessment = engine.assess_risk(
    satellite_signal=0.7,
    ai_signal=0.5,
    sensor_signal=0.6
)

print(assessment['risk_level'])      # HIGH_RISK
print(assessment['explanation'])     # Human-readable explanation
```

---

## 🔧 Configuration

Edit `.env` file to customize:

```ini
# Google Earth Engine
GEE_CREDENTIALS_PATH=./gee-credentials.json

# Project settings
PROJECT_NAME=G-ALERT
REGION=Himalayas
SIMULATION_MODE=False

# Risk thresholds (DEMO VALUES - customize as needed)
RISK_SAFE_THRESHOLD=0.2
RISK_WARNING_THRESHOLD=0.4
RISK_HIGH_RISK_THRESHOLD=0.7
RISK_CRITICAL_THRESHOLD=0.9

# Satellite settings
CLOUD_COVER_THRESHOLD=20
NDWI_WATER_THRESHOLD=0.3
```

---

## 📊 Data Flow

```
┌─────────────────┐
│  Sentinel-2     │
│  Satellite      │
└────────┬────────┘
         │
    Google Earth Engine
         │
    ┌────▼──────────────────────┐
    │  NDWI Analysis            │
    │  Water Detection          │
    └────┬──────────────────────┘
         │
    Satellite Signal (0-1)
         │
    ┌────┴────────────┬──────────────────┬────────────────┐
    │                 │                  │                │
    ▼                 ▼                  ▼                ▼
YOLOv8          Virtual Sensors    Risk Engine      Frontend
Detection       (Wokwi)            (Central Hub)    (Dashboard)
    │                 │                  │                │
    └─────AI Signal───┴─Sensor Signal────┴────Risk Level─┘
                      
                   RISK ASSESSMENT
```

---

## 🧪 Testing

### Test 1: Sensor Network
```bash
python -c "from simulation.sensor_simulator import SensorNetwork; net = SensorNetwork('test'); net.add_vibration_sensor('V1'); net.add_water_level_sensor('W1'); print(net.read_all_sensors())"
```

### Test 2: Nepal Scenario
```bash
python -c "from simulation.nepal_disaster import NepalDisasterScenario; s = NepalDisasterScenario(); [print(e['phase'].value) for e in s.event_sequence[:3]]"
```

### Test 3: Risk Engine
```bash
python -c "from risk_engine import RiskEngine; e = RiskEngine(); print(e.assess_risk(0.5, 0.6, 0.7)['risk_level'])"
```

### Test 4: Full Demo
```bash
python main.py
```

---

## 🎯 Next Steps

1. **GEE Authentication** - Set up Google Earth Engine credentials
2. **Satellite Connection Test** - Retrieve actual Sentinel-2 data
3. **NDWI Processing** - Calculate real water observations
4. **Risk Engine Tuning** - Adjust weights and thresholds
5. **Frontend Integration** - Output risk assessments as API/JSON
6. **Hackathon Demo** - Show Nepal scenario progression

---

## 📝 Notes for Hackathon Judges

**Demonstration Sequence:**

1. **Real Satellite Data** - Show Sentinel-2 NDWI analysis
2. **AI Detection** - YOLOv8 running on glacier imagery
3. **Virtual Sensors** - Wokwi simulation network active
4. **Nepal Scenario** - Run through all disaster phases
5. **Risk Progression** - Watch risk level escalate
6. **Alert Generation** - Show CRITICAL alert at peak

**Key Messages:**
- ✅ Multi-source data integration
- ✅ Automated risk assessment
- ✅ Early warning capability
- ✅ Extensible to real deployment
- ✅ Real satellite data (Google Earth Engine)
- ✅ Demo scenario for system validation

---

## 📚 References

- [Google Earth Engine Documentation](https://developers.google.com/earth-engine)
- [Sentinel-2 Bands](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-2-msi/resolutions/spatial)
- [NDWI Research](https://en.wikipedia.org/wiki/Normalized_difference_water_index)
- [YOLOv8 Docs](https://docs.ultralytics.com/)
- [GLOF Information](https://en.wikipedia.org/wiki/Glacial_lake_outburst_flood)

---

## 👥 Development Team

**Backend Developer:** [Your Name]  
**Frontend Developer:** [Team Member Name]

**Hackathon Project:** G-ALERT  
**Date:** 2026

---

## ⚖️ License & Attribution

This is a hackathon prototype created for educational and demonstration purposes.

---

**Last Updated:** September 2, 2026
