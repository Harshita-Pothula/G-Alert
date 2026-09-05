# G-ALERT Backend - Himalayan Glacial Lake Early Warning Prototype

**Smart India Hackathon (SIH) prototype** | Explainable glacial-lake *risk monitoring* (not operational GLOF prediction)

---

## Goal

Show how **real Sentinel-2 observations** (Google Earth Engine), **prototype satellite analysis**, **simulated sensors**, and **supporting signals** can be fused in a **Risk Engine** into an explainable risk level, plus catalog downstream-exposure context and a suggested action.

**This is a prototype, not an operational GLOF warning or prediction system.**

**What the current backend actually demonstrates:**
1. Multi-region glacial lake *monitoring boxes* via Sentinel-2 / GEE
2. Prototype NDWI / water-area analysis (including optional baseline comparison)
3. Generic YOLOv8 object detection for transparency only (`NO_DOMAIN_SIGNAL` — **not** a GLOF detector)
4. Virtual sensor network (Python simulation — **not** live Arduino/Wokwi telemetry)
5. Prototype risk scoring with explanation, action text, and per-call event history
6. Scripted Nepal Aug 26, 2026 disaster *simulation* (not a real or forecast event)

---

## Important Disclaimer

**THIS IS A PROTOTYPE / DEMO SYSTEM**

- Sentinel-2 observations come from **Google Earth Engine** (real imagery when authentication succeeds).
- Satellite analysis is a **prototype NDWI / water-area** method (demo-level processing, not a validated lake inventory or GLOF detector).
- All sensor readings are **SIMULATED**, not real measurements.
- The Nepal scenario is a **scripted simulation**, not real historical or forecast data.
- YOLOv8 (`yolov8n.pt`) is a **generic COCO object detector**. It is **not** trained for glacial lakes or GLOFs. Status `NO_DOMAIN_SIGNAL` means those detections are **not** treated as a valid GLOF-domain AI signal (contribution to GLOF risk is **0.0**).
- Risk **weights and thresholds** are **prototype/demo logic** in `risk_engine.py`. They are **not scientifically validated**.
- Downstream exposure text is **reference/context from the region catalog**, not a measured hydrologic model output.
- Evacuation guidance, if added later, must be labelled **demonstration information** unless validated by authorities.
- Suggested `action` strings are **not** dispatched alerts (no SMS/WhatsApp/siren in this phase).
- This system is **NOT** suitable for operational disaster prediction or public warning.

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
region_bounds = get_region_bounds("Tsho_Rolpa_Nepal")
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

**Pixel-level quality masking (live GEE path):** Before NDWI/water-area computation,
the pipeline applies Sentinel-2 SCL (Scene Classification Layer) masking, excluding
cloud shadow (3), medium/high-probability cloud (8/9), thin cirrus (10), and snow/ice
(11). Masking statistics (per-class fractions, valid-pixel fraction) are measured from
the actual image and reported in the observation under `satellite.quality_masking`.
**Limitation:** the NDWI water threshold (0.3, McFeeters 1996) is **not calibrated**
for Himalayan glacial lakes (`satellite.ndwi_threshold.validated` is always `false`),
and terrain shadow / turbid water remain known limitations.

**Key Classes:**
- `NDWIAnalyzer` - Calculates NDWI and water masks
- `WaterObservation` - Stores water observation data

**Example:**
```python
from satellite.ndwi_analysis import NDWIAnalyzer

analyzer = NDWIAnalyzer(ndwi_water_threshold=0.3)
ndwi = analyzer.calculate_ndwi(image)
water_mask = analyzer.create_water_mask(ndwi)
area = analyzer.calculate_water_area(water_mask, region_bounds)
```

### C. Region Configuration (`satellite/region_config.py`)

**Purpose:** Define and manage Himalayan monitoring regions

**Configured regions** (see `HIMALAYAN_REGIONS` in `satellite/region_config.py`):
- Nepal: Langtang Valley, Tsho Rolpa, Imja Tsho, Dig Tsho, Thulagi
- Bhutan: Thorthormi, Raphstreng Tsho
- Tibet / China: Longbasaba & Pida
- Karakoram boundary: Shaksgam
- India: Chorabari Tal (Kedarnath region)

These are documented lakes used as **monitoring sites**, not a complete Himalayan inventory.

### D. YOLOv8 Detector (`ai/yolov8_detector.py`)

**Purpose:** Generic object detection (COCO classes). **Not** a glacial-lake or GLOF detector.

In integrated monitoring, detections may be stored in JSON for transparency, but status is `NO_DOMAIN_SIGNAL` and the AI contribution to GLOF risk is **0.0**.

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

**Purpose:** Generate **simulated** sensor readings (vibration, water level, rainfall). Not connected to physical Wokwi/Arduino hardware in this backend.

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

**Purpose:** Scripted Nepal Aug 26, 2026 flash-flood *simulation* for demos. All sensor/satellite/AI values in the scenario are generated. This is not a real event.

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

**Purpose:** Combine satellite, AI, and sensor **signals** (0–1) into a prototype risk level.

**Risk Levels (prototype cutoffs in code, not validated science):**
- `SAFE` (score 0.0 - 0.3)
- `WARNING` (score 0.3 - 0.6)
- `HIGH_RISK` (score 0.6 - 0.85)
- `CRITICAL` (score 0.85 - 1.0)

**Signal weights (prototype, currently 40% / 30% / 30%):**
- Satellite: 40%
- AI: 30% (generic YOLO is forced to 0.0 in the integrated GEE path)
- Sensor: 30%

`action` and `explanation` live **inside** the `risk` object. Per-call `history` is the RiskEngine instance list (often length 1).

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

## Integrated JSON (Streamlit contract)

Both live monitoring and the Nepal simulation return the same **top-level keys**:

`status`, `region`, `satellite`, `satellite_change`, `sensors`, `ai`, `risk`, `downstream_exposure`, `history`

- **Frontend must not calculate** risk score, risk level, weights, or thresholds. Display `risk` from the backend Risk Engine only.
- Warning/action are **inside** `risk` (`action`, `explanation`).
- **Simulation phase** (NORMAL → INCIDENT) is the scripted story (`simulation_phase`). **`risk.risk_level`** is the engine assessment. They are not required to match.

### A. Pan-Himalayan monitoring (real Sentinel-2 / GEE)

```python
from main import run_integrated_monitoring

observation = run_integrated_monitoring("Tsho_Rolpa_Nepal")  # mode defaults to "monitoring"
```

- Uses Google Earth Engine. If GEE fails, returns an honest error envelope (`status=ERROR` or `NO_SUITABLE_IMAGERY`). Does **not** invent satellite imagery.
- Sensors stay `NOT_RUN` in monitoring mode (no silent simulated telemetry).
- Generic YOLO, if present, is `NO_DOMAIN_SIGNAL` with GLOF AI contribution **0.0**.

### B. Nepal simulation (no GEE)

```python
from main import NepalDisasterScenario, run_nepal_simulation_step, run_nepal_simulation_sequence

# Full five-phase run, one shared RiskEngine (history length 5):
steps = run_nepal_simulation_sequence()

# Or step through for the UI:
scenario = NepalDisasterScenario()
step = run_nepal_simulation_step(scenario)  # repeat; returns None when finished
```

- `mode` is `nepal_simulation`. Does **not** call GEE; works if Earth Engine is unavailable.
- Sensors, simulated NDWI/area, and simulated AI anomaly are labelled `simulated: true`.
- Nepal AI is a **scripted supporting signal**, not YOLOv8.

---

## 🔧 Configuration

GEE credentials are read from `.env` (`GEE_CREDENTIALS_PATH`, `GEE_PROJECT_ID` / `GOOGLE_CLOUD_PROJECT`).

**Risk weights and thresholds are defined in `risk_engine.py`**, not currently loaded from `.env`. Do not treat `.env` `RISK_*` examples as live engine settings unless that wiring is added later.

Satellite cloud/NDWI demo defaults live in the GEE pipeline and `NDWIAnalyzer` (NDWI water threshold default 0.3).

Example `.env` for Earth Engine:

```ini
GEE_CREDENTIALS_PATH=./gee-credentials.json
GEE_PROJECT_ID=your-gcp-project
```

---

## 📊 Data Flow (prototype)

```
Sentinel-2 (GEE, monitoring) → NDWI / water-area / baseline (prototype)
        → satellite signal (0-1)
Monitoring sensors: NOT_RUN unless an explicit simulation mode is requested
Generic YOLOv8 (monitoring) → NO_DOMAIN_SIGNAL → AI GLOF signal = 0.0
Nepal simulation: scripted sensors + simulated NDWI/AI (labelled simulated)
        → Risk Engine (single source of risk_level)
        → explanation + action
        → downstream_exposure (catalog text, when present)
        → history (one engine instance per Nepal run)
```

There is no Flask HTTP API. Streamlit should import `run_integrated_monitoring` and `run_nepal_simulation_step` / `run_nepal_simulation_sequence`.

---

## Dependency inventory (do not uninstall yet)

Recorded for a later decision with the Streamlit / teammate stack. **Nothing was removed in Phase 1.**

| Dependency | In `requirements.txt` | Used by current backend code? |
|---|---|---|
| earthengine-api | yes | Yes — `satellite/gee_pipeline.py`, NDWI GEE path, GEE tests |
| python-dotenv | yes | Yes — GEE pipeline and GEE tests |
| numpy | yes | Yes — `satellite/ndwi_analysis.py` (numeric/demo branch) |
| ultralytics, torch, torchvision | yes | Yes — `ai/yolov8_detector.py` (optional; integrated path degrades if missing) |
| requests | yes | Not imported in app modules (may be used transitively) |
| python-dateutil | yes | Not imported in app modules |
| Flask | yes | **Not used** (no Flask app) |
| PyArduino | yes | **Not imported**; package name is questionable on PyPI |
| pandas, rasterio, geopandas | yes | **Not imported** in current backend modules |
| numpy/pandas GIS stack | — | GEE analysis uses Earth Engine reducers, not rasterio locally |

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

### Test 5: Phase 1 integrated contract (no live GEE)
```bash
python phase1_integrated_test.py
```

### Test 6: Phase 2 Nepal integration (no live GEE)
```bash
python phase2_nepal_test.py
```

### Test 7: Full Demo
```bash
python main.py
```
Live GEE, YOLO, and torch are environment-dependent.

---

## Next steps (later phases)

- Alert provider interface (no SMS until a teammate chooses a provider)
- Streamlit UI consuming the JSON keys above

Do not treat Risk Engine weight/threshold retuning as a default next step.

---

## Notes for hackathon judges

**Honest demonstration:**

1. **Real satellite data** — Sentinel-2 via Google Earth Engine (when auth works)
2. **Prototype NDWI / water-area** — not a validated GLOF predictor
3. **Generic YOLOv8** — COCO detections may appear; they do **not** raise GLOF risk (`NO_DOMAIN_SIGNAL`)
4. **Virtual sensors** — simulated Python readings, not live field instruments
5. **Nepal scenario** — scripted simulation to show escalation
6. **Risk Engine** — prototype weighted score, explanation, and action text
7. **Downstream exposure** — catalog/reference context, not a flood model

**Do not claim:** operational early warning, real-time GLOF prediction, or YOLO-based glacial-lake detection.

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

**Last Updated:** September 3, 2026 (Phase 1 documentation)
