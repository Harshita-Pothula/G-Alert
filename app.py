"""
app.py - Flask API for G-ALERT backend
Exposes existing functionality as clean JSON endpoints for frontend, sensor, and alert teams
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from satellite.region_config import HIMALAYAN_REGIONS, get_region_info
from main import (
    run_integrated_monitoring,
    run_nepal_simulation_sequence,
    run_temporal_evidence,
    run_tsho_rolpa_temporal_evidence,
)
from simulation.sensor_simulator import SensorNetwork
from risk_engine import RiskEngine
from observation_store import ObservationStore

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend consumption

# Configuration
app.config['JSON_SORT_KEYS'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True


def _validated_signal(data, name, default):
    """Return a numeric signal in the inclusive 0-1 range."""
    value = data.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number between 0 and 1")
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be a number between 0 and 1")
    return float(value)


# ============================================================================
# HEALTH & SYSTEM ENDPOINTS
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """System health check for monitoring and team coordination."""
    try:
        import ee
        ee_authenticated = ee.data.isInitialized()
    except:
        ee_authenticated = False
    
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "services": {
            "flask_running": True,
            "gee_authenticated": ee_authenticated
        },
        "data_source_classification": "SYSTEM_STATUS"
    })


# ============================================================================
# REGION INFORMATION ENDPOINTS
# ============================================================================

@app.route('/api/regions', methods=['GET'])
def get_regions():
    """Return all available monitoring regions for frontend selection."""
    regions = []
    for key, region in HIMALAYAN_REGIONS.items():
        regions.append({
            "key": key,
            "name": region["name"],
            "lake_name": region["lake_name"],
            "country": region["country"],
            "coordinates": {
                "latitude": region["latitude"],
                "longitude": region["longitude"]
            },
            "elevation_m": region.get("elevation_m"),
            "hazard_level": region.get("hazard_level", "UNKNOWN"),
            "lake_type": region.get("lake_type", "UNKNOWN")
        })
    
    return jsonify({
        "status": "success",
        "data_source": "CONFIGURED_REGIONS",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "count": len(regions),
        "regions": regions
    })


@app.route('/api/regions/<region_key>', methods=['GET'])
def get_region_detail(region_key):
    """Return detailed information about a specific region."""
    region = get_region_info(region_key)
    
    if region is None:
        return jsonify({
            "status": "error",
            "error": f"Region '{region_key}' not found",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }), 404
    
    return jsonify({
        "status": "success",
        "data_source": "CONFIGURED_REGIONS",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "region": region
    })


# ============================================================================
# SATELLITE MONITORING ENDPOINTS (CORE FUNCTIONALITY)
# ============================================================================

@app.route('/api/monitor/<region_key>', methods=['GET'])
def monitor_region(region_key):
    """
    Live satellite monitoring for a specific region.
    This is the core endpoint that uses real GEE data and actual calculations.
    """
    # Query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    mode = request.args.get('mode', 'monitoring')

    if mode not in {'monitoring', 'simulation'}:
        return jsonify({"status": "error", "error": "mode must be monitoring or simulation"}), 400
    
    try:
        observation = run_integrated_monitoring(
            region_key=region_key,
            start_date=start_date,
            end_date=end_date,
            mode=mode
        )
        
        # Add data source classification if not present
        if 'data_source' not in observation:
            if mode == 'monitoring':
                observation['data_source'] = 'LIVE_SENTINEL2'
            else:
                observation['data_source'] = 'SIMULATION'
        
        # Add API metadata
        observation['api_metadata'] = {
            "api_version": "1.0",
            "response_type": "regional_analysis",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "processing_mode": mode
        }
        
        return jsonify(observation)
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "region": region_key,
            "error": str(e),
            "data_source": "ERROR",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }), 500


@app.route('/api/monitor/multi', methods=['POST'])
def monitor_multiple_regions():
    """Monitor multiple regions in parallel for comparison."""
    data = request.get_json() or {}
    region_keys = data.get('regions', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    mode = data.get('mode', 'monitoring')
    
    if not isinstance(region_keys, list) or not region_keys or len(region_keys) > 10:
        return jsonify({
            "status": "error",
            "error": "regions must be a non-empty list of at most 10 region keys",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }), 400

    if mode not in {'monitoring', 'simulation'}:
        return jsonify({"status": "error", "error": "mode must be monitoring or simulation"}), 400
    
    results = []
    errors = []
    
    for region_key in region_keys:
        try:
            observation = run_integrated_monitoring(
                region_key=region_key,
                start_date=start_date,
                end_date=end_date,
                mode=mode
            )
            
            if 'data_source' not in observation:
                observation['data_source'] = 'LIVE_SENTINEL2' if mode == 'monitoring' else 'SIMULATION'
            
            results.append(observation)
        except Exception as e:
            errors.append({
                "region": region_key,
                "error": str(e)
            })
    
    return jsonify({
        "status": "success",
        "data_source": "LIVE_SENTINEL2" if mode == 'monitoring' else 'SIMULATION',
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "requested_regions": len(region_keys),
        "successful_analyses": len(results),
        "failed_analyses": len(errors),
        "results": results,
        "errors": errors
    })


@app.route('/api/observations/<region_key>', methods=['GET'])
def get_observation_history(region_key):
    """Return persisted monitoring observations for one configured region."""
    if get_region_info(region_key) is None:
        return jsonify({"status": "error", "error": f"Region '{region_key}' not found"}), 404
    limit = request.args.get('limit', default=50, type=int)
    try:
        observations = ObservationStore().list(region_key, limit)
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400
    return jsonify({
        "status": "success",
        "region": region_key,
        "count": len(observations),
        "observations": observations,
    })


@app.route('/api/observations/<region_key>/temporal', methods=['GET'])
def get_temporal_observation_history(region_key):
    """Return persisted multi-date evidence runs for one configured region."""
    if get_region_info(region_key) is None:
        return jsonify({"status": "error", "error": f"Region '{region_key}' not found"}), 404
    limit = request.args.get('limit', default=20, type=int)
    try:
        runs = ObservationStore().list_temporal_evidence(region_key, limit)
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400
    return jsonify({
        "status": "success",
        "region": region_key,
        "count": len(runs),
        "temporal_evidence_runs": runs,
    })


@app.route('/api/monitor/Tsho_Rolpa_Nepal/temporal', methods=['GET'])
def monitor_tsho_rolpa_temporal():
    """Evaluate multi-date satellite candidate consistency for Tsho Rolpa."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    max_observations = request.args.get('max_observations', default=6, type=int)
    try:
        result = run_tsho_rolpa_temporal_evidence(start_date, end_date, max_observations)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400
    except Exception:
        return jsonify({"status": "error", "error": "Temporal monitoring failed"}), 500


@app.route('/api/monitor/<region_key>/temporal', methods=['GET'])
def monitor_region_temporal(region_key):
    """Evaluate multi-date satellite candidate consistency for any configured region."""
    if get_region_info(region_key) is None:
        return jsonify({
            "status": "error",
            "error": f"Region '{region_key}' not found",
        }), 404
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    max_observations = request.args.get('max_observations', default=6, type=int)
    try:
        return jsonify(run_temporal_evidence(
            region_key, start_date, end_date, max_observations
        ))
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400
    except Exception:
        return jsonify({"status": "error", "error": "Temporal monitoring failed"}), 500


@app.route('/api/monitor/multi/temporal', methods=['POST'])
def monitor_multiple_regions_temporal():
    """Run the reusable real-satellite temporal workflow for several regions."""
    data = request.get_json() or {}
    region_keys = data.get("regions", [])
    if not isinstance(region_keys, list) or not region_keys or len(region_keys) > 10:
        return jsonify({
            "status": "error",
            "error": "regions must be a non-empty list of at most 10 region keys",
        }), 400
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    max_observations = data.get("max_observations", 6)
    if not isinstance(max_observations, int):
        return jsonify({"status": "error", "error": "max_observations must be an integer"}), 400
    results = []
    errors = []
    for region_key in region_keys:
        if get_region_info(region_key) is None:
            errors.append({"region": region_key, "error": "Region not found"})
            continue
        try:
            results.append(run_temporal_evidence(
                region_key, start_date, end_date, max_observations
            ))
        except Exception as exc:
            errors.append({"region": region_key, "error": str(exc)})
    return jsonify({
        "status": "success",
        "data_source": "LIVE_SENTINEL2",
        "requested_regions": len(region_keys),
        "successful_analyses": len(results),
        "failed_analyses": len(errors),
        "results": results,
        "errors": errors,
    })


# ============================================================================
# SENSOR INTEGRATION ENDPOINTS
# ============================================================================

@app.route('/api/sensors/simulate', methods=['POST'])
def simulate_sensors():
    """
    Generate simulated sensor readings for demonstration.
    Clearly labeled as simulation data.
    """
    data = request.get_json() or {}
    location = data.get('location', 'Nepal_Pokhara')
    anomaly_factors = data.get('anomaly_factors')
    
    network = SensorNetwork(location)
    network.add_vibration_sensor("VIB-001")
    network.add_water_level_sensor("WATER-001", normal_level=150)
    network.add_rainfall_sensor("RF-001")
    
    readings = network.read_all_sensors(anomaly_factors=anomaly_factors)
    
    return jsonify({
        "status": "success",
        "data_source": "SIMULATED_SENSORS",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "location": location,
        "sensor_readings": readings,
        "note": "Simulated virtual sensor readings - NOT real measurements"
    })


@app.route('/api/sensors/status/<region_key>', methods=['GET'])
def get_sensor_status(region_key):
    """Return sensor network status for a region (placeholder for real sensor integration)."""
    region = get_region_info(region_key)
    
    if region is None:
        return jsonify({
            "status": "error",
            "error": f"Region '{region_key}' not found",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }), 404
    
    # Placeholder for real sensor integration
    return jsonify({
        "status": "success",
        "data_source": "SENSOR_STATUS_PLACEHOLDER",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "region": region_key,
        "sensor_network_status": {
            "network_id": f"{region_key.upper()}_SENSOR_NETWORK",
            "sensors_deployed": 0,
            "sensors_active": 0,
            "last_reading": None,
            "integration_status": "PENDING_HARDWARE_TEAM",
            "note": "Real sensor integration pending hardware team deployment"
        }
    })


# ============================================================================
# RISK ENGINE DEMO ENDPOINTS
# ============================================================================

@app.route('/api/demo/risk-engine', methods=['POST'])
def demo_risk_engine():
    """Risk engine assessment demonstration using existing logic."""
    data = request.get_json() or {}
    engine = RiskEngine()
    
    # Use provided values or defaults
    try:
        satellite_signal = _validated_signal(data, 'satellite_signal', 0.1)
        ai_signal = _validated_signal(data, 'ai_signal', 0.05)
        sensor_signal = _validated_signal(data, 'sensor_signal', 0.15)
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400
    
    assessment = engine.assess_risk(
        satellite_signal=satellite_signal,
        ai_signal=ai_signal,
        sensor_signal=sensor_signal,
        region=data.get('region')
    )
    
    return jsonify({
        "status": "success",
        "data_source": "RISK_ENGINE_CALCULATION",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "assessment": assessment,
        "input_parameters": {
            "satellite_signal": satellite_signal,
            "ai_signal": ai_signal,
            "sensor_signal": sensor_signal
        },
        "note": "Risk engine calculation using existing prototype weights and thresholds"
    })


# ============================================================================
# NEPAL SIMULATION ENDPOINTS (CLEARLY LABELED AS SIMULATION)
# ============================================================================

@app.route('/api/simulation/nepal-flood', methods=['GET'])
def nepal_flood_simulation():
    """
    Nepal August 26, 2026 flood simulation.
    CLEARLY LABELED AS SIMULATION - NOT A REAL PREDICTION.
    """
    try:
        steps = run_nepal_simulation_sequence()
        
        return jsonify({
            "status": "success",
            "data_source": "SCIENTIFIC_SIMULATION",
            "simulation_type": "NEPAL_FLOOD_AUGUST_2026",
            "transparency_note": "This is a scientifically-grounded simulation based on GLOF mechanics for demonstration purposes. It is NOT a prediction of real events or a claim that G-ALERT predicted this event.",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_phases": len(steps),
            "simulation_steps": steps
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "data_source": "SIMULATION_ERROR",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }), 500


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": "error",
        "error": "Endpoint not found",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "status": "error",
        "error": "Internal server error",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }), 500


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("G-ALERT Backend API Server")
    print("="*60)
    print("Starting Flask server...")
    print("API endpoints available:")
    print("  GET  /api/health")
    print("  GET  /api/regions")
    print("  GET  /api/regions/<region_key>")
    print("  GET  /api/monitor/<region_key>")
    print("  POST /api/monitor/multi")
    print("  POST /api/sensors/simulate")
    print("  GET  /api/sensors/status/<region_key>")
    print("  POST /api/demo/risk-engine")
    print("  GET  /api/simulation/nepal-flood")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False)