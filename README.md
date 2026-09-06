# G-ALERT Backend

G-ALERT is a student hackathon prototype for monitoring Himalayan glacial lakes and exploring possible **Glacial Lake Outburst Flood (GLOF)** risk.

It combines real satellite observations, external weather evidence, persisted telemetry, identity validation, evidence status, and prototype decision support. It is an explainable learning system, not an operational warning system or a validated GLOF prediction model.

## What It Does

The backend monitors configured Himalayan regions using:

- **Sentinel-2 through Google Earth Engine:** real imagery from `COPERNICUS/S2_SR_HARMONIZED`.
- **NDWI and water-area processing:** SCL quality masking is applied before water detection and area reduction.
- **Previous-observation comparison:** current observed water area is compared with the newest prior valid observation.
- **Seasonal baseline evidence:** same-calendar-period historical observations are evaluated separately from previous-observation change.
- **Open-Meteo weather:** current and recent rainfall are kept as weather evidence.
- **ESP32/Wokwi telemetry:** accepted telemetry is persisted in SQLite and fresh readings can provide IoT sensor evidence.
- **Prototype Risk Engine:** combines bounded signals without claiming a validated GLOF probability.
- **Evidence-only cross-validation:** compares available satellite, weather, and sensor evidence without inventing agreement or causation.
- **Generic YOLOv8 transparency output:** generic detections are not a GLOF signal and contribute zero to GLOF risk.

The backend keeps real, simulated, stale, withheld, and unavailable evidence labelled separately.

## Monitoring Flow

```text
Sentinel-2 / Google Earth Engine
        |
        v
SCL mask -> NDWI -> water area -> previous change / seasonal baseline
        |
Open-Meteo weather --------------------+
Fresh persisted ESP32 telemetry --------+--> evidence and Risk Engine
Generic YOLOv8 (NO_DOMAIN_SIGNAL) ------+
        |
        v
Risk result, explanation, warning status, provenance, and history
```

The normal endpoint is:

```text
GET /api/monitor/<region_key>
```

Normal monitoring uses real data only. Use the explicit simulation endpoints or `mode=simulation` only for demonstrations.

## Evidence Sources and Status

The response keeps these four sources separate:

| Source | Current meaning |
|---|---|
| `satellite` | Real Sentinel-2-derived evidence, including NDWI, quality masking, water area, identity context, and change evidence |
| `weather` | Real Open-Meteo rainfall evidence only |
| `sensors` / sensor signal | Fresh persisted ESP32/IoT telemetry only |
| `ai` | Generic YOLO transparency output; currently `NO_DOMAIN_SIGNAL` and zero GLOF contribution |

Evidence can be reported as `AVAILABLE`, `UNAVAILABLE`, `STALE`, `WITHHELD`, `SIMULATED`, `NO_DOMAIN_SIGNAL`, or `INSUFFICIENT_EVIDENCE`, depending on the source and processing path.

### Weather

Open-Meteo is never treated as ESP32 telemetry. Its fields include rainfall values, source, observation time, provenance, and a separate weather signal. Weather may be available even when IoT telemetry is unavailable.

### IoT Sensors

Telemetry is accepted at `POST /api/sensors/telemetry` and persisted in the existing SQLite database. The monitoring workflow selects the newest reading per sensor:

- Fresh telemetry can contribute to the IoT sensor signal.
- Stale telemetry remains visible as stale evidence but does not contribute to live risk.
- Missing telemetry remains unavailable; `risk.signals.sensor` can be `null`.
- Simulated/Wokwi telemetry remains explicitly marked as simulated.
- Missing evidence is never interpreted as SAFE.

Supported sensor types and units include:

- `vibration`: `cm/s`
- `water_level`: `cm` or `m`
- `rainfall`: `mm/h`, `mm/hr`, or `mm/hour`

Example telemetry payload:

```json
{
  "sensor_id": "WOKWI-VIB-001",
  "region_key": "Tsho_Rolpa_Nepal",
  "sensor_type": "vibration",
  "timestamp": "2026-09-06T12:00:00Z",
  "reading": {
    "value": 4.2,
    "unit": "cm/s"
  },
  "sequence": 1,
  "simulated": true,
  "provenance": "Wokwi ESP32 prototype telemetry"
}
```

## Satellite Evidence

`Sentinel2Pipeline` retrieves real Sentinel-2 Surface Reflectance imagery through Earth Engine. `NDWIAnalyzer`:

1. Applies Sentinel-2 SCL quality masking.
2. Excludes cloud shadow, medium/high-probability cloud, thin cirrus, and snow/ice classes.
3. Calculates NDWI using Sentinel-2 green and NIR bands.
4. Creates a water mask using the current prototype threshold.
5. Calculates water area from real Earth Engine pixels.

The default NDWI threshold is a general prototype threshold and is not calibrated for Himalayan glacial lakes. Terrain shadow and turbid water remain limitations.

Two change concepts remain separate:

- **Previous-observation change:** current area versus the newest prior valid observation. This is the comparison used by the satellite signal path when a valid previous area exists.
- **Seasonal baseline change:** current area versus valid same-calendar-period historical observations. This is contextual evidence and does not replace the previous-observation comparison.

An expanded Sentinel-2 search window, when used, is marked as fallback imagery with the actual acquisition date and provenance.

## Risk Engine

The Risk Engine uses prototype parameters:

- Satellite: `40%`
- AI: `30%`
- IoT sensor: `30%`

The current live weather signal is kept separate from the IoT sensor signal. Existing Risk Engine calculations, weights, thresholds, scores, and signal formulas are prototype logic and are not scientifically validated GLOF probabilities.

Risk levels are:

```text
SAFE       score below 0.30 when required evidence is complete
WARNING    score from 0.30 to below 0.60
HIGH_RISK  score from 0.60 to below 0.85
CRITICAL   score from 0.85 upward
UNKNOWN    required or withheld evidence prevents a definitive level
```

A valid monitoring pipeline can complete with:

```text
overall status: SUCCESS
risk level: UNKNOWN
assessment status: LIMITED_CONFIDENCE
system status: INSUFFICIENT_DATA
```

This is an explicit insufficient-evidence result, not a system failure and not SAFE. Missing or withheld evidence is never evidence of safety.

### Risk Explanation Fields

Existing `risk.explanation` remains the compatible human-readable string. The additive `risk.explanation_detail` field explains:

- Final risk level, score, confidence, and assessment status.
- Satellite contribution and relevant satellite details.
- Open-Meteo weather status and whether it affected the assessment.
- IoT sensor status, freshness, contribution, or unavailability.
- AI status and limitations.
- Evidence that contributed.
- Evidence that was unavailable, stale, simulated, or withheld.
- Important prototype limitations.

The AI explanation explicitly states that generic YOLOv8 is not a GLOF-domain model and contributes zero to GLOF risk. `risk.signal_sources` identifies the source behind each signal.

## Execution and Warning Status

Monitoring responses include an `execution` summary with fields such as:

- `execution.job_status`
- `execution.completed_stages`
- `execution.failed_stage`
- `execution.failure_reason`
- `execution.system_status`

An execution failure indicates an orchestration or processing problem. `INSUFFICIENT_DATA` can instead be a valid evidence outcome after a real observation is processed.

The response also includes:

- `early_warning_status`: system-level `NORMAL`, `WATCH`, `WARNING`, `UNCONFIRMED`, or `INSUFFICIENT_DATA`.
- `human_warning`: plain-language warning interpretation and recommended action.
- `alert_confirmation`: confirmation and persistence state for repeated warning observations.
- `cross_validation`: evidence-only comparison status.
- `data_confidence`: evidence quality summary, not a probability.
- `provenance`: source and limitation metadata.

The alert lifecycle stores verified warning events, rejects simulated or unavailable evidence, requires provenance, and prevents duplicate active conditions. It is an internal lifecycle/audit capability only. **Twilio, SMS, WhatsApp, siren, and public alert dispatch are not implemented.**

## Tsho Rolpa

Tsho Rolpa intentionally demonstrates responsible evidence withholding. It may return:

- `IDENTITY_AMBIGUOUS`
- `IDENTITY_NOT_ESTABLISHED`
- `INSUFFICIENT_DATA`
- withheld or unavailable area measurements

This behavior preserves strict candidate identity, trusted-boundary, temporal, and baseline gates. Tsho Rolpa must not be described as SAFE or as an ordinary system error merely because a definitive named-lake assessment was not established.

## AI / ML

The repository includes a generic pretrained `yolov8n.pt` model through Ultralytics. It performs generic object detection for transparency and demo output. It is not trained for GLOF, glacial lakes, moraine dams, or flood prediction.

The integrated live path reports:

```text
ai.status = NO_DOMAIN_SIGNAL
ai.signal = 0.0
risk.signals.ai = 0.0
```

No domain-specific dataset, custom GLOF weights, or validated GLOF model is included. A future domain model should remain advisory until it has suitable labelled data and scientific validation.

## Real Monitoring and Simulation

Real monitoring uses the normal monitoring endpoint and real external evidence. Simulation remains separate:

- `mode=simulation` uses the existing virtual sensor demonstration path.
- `GET /api/simulation/nepal-flood` runs the separate scripted Nepal scenario.
- Simulation evidence is explicitly marked and must not be presented as field observation.
- Generic YOLO remains zero-contribution in both the real GLOF path and the generic transparency path.

## Project Structure

This is a focused structure summary, not a complete file inventory:

```text
G-ALERT-backend/
├── app.py                         # Flask API entrypoint
├── main.py                        # Integrated monitoring orchestration
├── risk_engine.py                 # Prototype risk calculation
├── observation_store.py           # SQLite observations and telemetry
├── sensor_telemetry.py            # Validation and freshness contracts
├── weather_integration.py         # Open-Meteo adapter
├── alert_event_lifecycle.py       # Verified warning lifecycle
├── audit_trail.py                 # Append-only alert audit records
├── execution_manager.py           # Monitoring execution stages
├── satellite/                     # GEE, NDWI, detection, identity, cache
├── ai/                            # Generic YOLO wrapper
├── simulation/                    # Virtual sensors and Nepal scenario
├── wokwi/                         # ESP32/Wokwi sender and diagram
├── tests/                         # Additional focused tests
├── gee_cache/                     # Runtime GEE/downstream cache
├── requirements.txt
├── README.md
└── .gitignore
```

Other root modules and tests support provenance, identity, baselines, cross-validation, downstream context, impact screening, and regression coverage.

## Installation

Use Python 3.11 if possible:

```bash
pip install -r requirements.txt
```

The requirements include the runtime packages and the declared pytest test dependency. Some satellite, connectivity, and YOLO tests also require network access, Earth Engine authentication, or optional model packages.

### Google Earth Engine

The live satellite path requires Earth Engine authentication. For a service account, configure local environment variables such as:

```ini
GEE_CREDENTIALS_PATH=./gee-credentials.json
GEE_PROJECT_ID=your-gcp-project
```

Interactive Earth Engine authentication is also supported. Credential files are local secrets and must not be committed.

## Running the Backend

### Flask API

From the repository root:

```bash
python app.py
```

The API listens on port `5000`.

### Python Demo

```bash
python main.py
```

The demo includes virtual sensors, the scripted Nepal scenario, prototype risk examples, and configured regions. Simulation output is labeled as simulation.

### Wokwi ESP32 Prototype

Open `wokwi/diagram.json` in Wokwi or the Wokwi VS Code extension. The sketch:

- Connects to `Wokwi-GUEST` WiFi.
- Uses NTP for UTC timestamps.
- Sends vibration, water-level, and rainfall payloads every 30 seconds.
- Marks readings as simulated Wokwi prototype telemetry.
- Sends to the backend URL configured in `wokwi/sketch.ino`.

A cloud Wokwi simulation may need Gateway host access or a tunnel to reach Flask on a local computer.

## API Endpoints

### System and Regions

```text
GET  /api/health
GET  /api/regions
GET  /api/regions/<region_key>
```

### Monitoring

```text
GET  /api/monitor/<region_key>
POST /api/monitor/multi
GET  /api/monitor/<region_key>/temporal
GET  /api/monitor/Tsho_Rolpa_Nepal/temporal
POST /api/monitor/multi/temporal
```

### Sensor Telemetry

```text
POST /api/sensors/telemetry
GET  /api/sensors/status/<region_key>
GET  /api/sensors/telemetry/<sensor_id>/latest
GET  /api/sensors/telemetry/<region_key>/history
POST /api/sensors/simulate
```

### Other Demos and History

```text
GET  /api/observations/<region_key>
GET  /api/observations/<region_key>/temporal
POST /api/demo/risk-engine
GET  /api/simulation/nepal-flood
```

## Testing

Focused telemetry and evidence tests can be run directly:

```bash
python sensor_telemetry_test.py
python sensor_telemetry_api_test.py
python sensor_telemetry_persistence_test.py
python sensor_monitoring_integration_test.py
python monitoring_evidence_validation_test.py
```

Core prototype checks:

```bash
python risk_engine_test.py
python phase1_integrated_test.py
python phase2_nepal_test.py
python backend_quality_test.py
python production_execution_integration_test.py
```

The pytest suite can be run after installing the declared dependencies:

```bash
python -m pytest -q
```

Some satellite and connectivity tests require Earth Engine authentication, network access, or optional ML packages. Use isolated temporary databases for tests that exercise persistence so stale live telemetry does not affect results.

## Current Limitations

- This is a hackathon prototype, not an operational GLOF warning system.
- Risk weights, thresholds, and signals are not scientifically validated GLOF probabilities.
- Missing or withheld evidence is not evidence of safety.
- IoT availability may be limited; missing telemetry remains unavailable rather than being replaced with fake data.
- Wokwi and Python sensor readings are simulated, not field measurements.
- No physical Arduino or ESP32 hardware is connected to the backend yet.
- The NDWI threshold is not calibrated for Himalayan glacial lakes.
- Configured regions use approximate monitoring geometry unless trusted reference geometry is available.
- Named-lake identity can remain `IDENTITY_AMBIGUOUS` when temporal persistence or trusted reference evidence is missing.
- Seasonal comparison can be `INSUFFICIENT_HISTORICAL_DATA` when too few valid same-period real acquisitions are available.
- Cross-validation reports insufficient or unavailable evidence rather than forcing agreement.
- Generic YOLOv8 is not a GLOF or glacial-lake detector and contributes zero domain-specific AI risk.
- Downstream impact mapping is approximate screening, not hydrodynamic flood simulation.
- Weather, Earth Engine, Wokwi networking, and external data providers depend on network access and authentication.
- Twilio, SMS, WhatsApp, siren, and public alert dispatch are not implemented.

## Project Note

G-ALERT is built to make a complicated disaster-monitoring idea easier to explore: combine multiple signals, keep provenance visible, show uncertainty honestly, and let students extend the system step by step.
