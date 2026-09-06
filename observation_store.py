"""Durable storage for G-ALERT monitoring observation envelopes."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from region_integrity import validate_observation, require_valid_region


class ObservationStore:
    """Small SQLite-backed observation store for reproducible monitoring history."""

    def __init__(self, database_path=None):
        configured_path = database_path or os.getenv(
            "G_ALERT_OBSERVATIONS_DB", "g_alert_observations.sqlite3"
        )
        self.database_path = Path(configured_path)
        if self.database_path.parent != Path("."):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self):
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS observations (
                    observation_id TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    region TEXT NOT NULL,
                    mode TEXT,
                    status TEXT NOT NULL,
                    satellite_status TEXT,
                    identity_status TEXT,
                    decision_support_status TEXT,
                    measurement_status TEXT,
                    image_id TEXT,
                    acquisition_time TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_observations_region_time "
                "ON observations(region, recorded_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS temporal_evidence_runs (
                    run_id TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    region TEXT NOT NULL,
                    status TEXT NOT NULL,
                    identity_status TEXT,
                    requested_start TEXT,
                    requested_end TEXT,
                    observation_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_temporal_region_time "
                "ON temporal_evidence_runs(region, recorded_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sensor_telemetry (
                    telemetry_id TEXT PRIMARY KEY,
                    deduplication_key TEXT NOT NULL UNIQUE,
                    sensor_id TEXT NOT NULL,
                    region_key TEXT NOT NULL,
                    sensor_type TEXT NOT NULL,
                    telemetry_timestamp TEXT NOT NULL,
                    reading_value REAL NOT NULL,
                    reading_unit TEXT NOT NULL,
                    sequence INTEGER,
                    received_at TEXT NOT NULL,
                    freshness TEXT NOT NULL,
                    simulated INTEGER,
                    provenance_json TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sensor_telemetry_sensor_time "
                "ON sensor_telemetry(sensor_id, telemetry_timestamp DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sensor_telemetry_region_time "
                "ON sensor_telemetry(region_key, telemetry_timestamp DESC)"
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(observations)")
            }
            if "decision_support_status" not in columns:
                connection.execute(
                    "ALTER TABLE observations ADD COLUMN decision_support_status TEXT"
                )

    def save(self, observation):
        """Persist one complete JSON-safe monitoring result and return its ID."""
        region = validate_observation(observation)
        measurement = observation.get("observed_measurement") or {}
        identity_status = (
            (observation.get("temporal_evidence") or {}).get("identity_status")
            or ((observation.get("satellite") or {}).get("candidate_detection") or {}).get("identity_status")
            or observation.get("identity_status")
        )
        if isinstance(measurement.get("area_sqkm"), (int, float)) and identity_status != "IDENTITY_SUPPORTED":
            raise ValueError("Observed area requires IDENTITY_SUPPORTED")
        measurement_status = measurement.get("status")
        if measurement_status is None and identity_status != "IDENTITY_SUPPORTED":
            measurement_status = "UNAVAILABLE"
        payload_json = json.dumps(observation, sort_keys=True, allow_nan=False)
        decision_support_status = (
            (observation.get("decision_support") or {}).get("status")
        )
        satellite = observation.get("satellite") or {}
        candidate_detection = satellite.get("candidate_detection") or {}
        observation_id = str(uuid.uuid4())
        recorded_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO observations (
                    observation_id, recorded_at, region, mode, status,
                    satellite_status, identity_status, decision_support_status, measurement_status,
                    image_id, acquisition_time, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    recorded_at,
                    region,
                    observation.get("mode"),
                    observation.get("status", "UNKNOWN"),
                    satellite.get("status"),
                    identity_status,
                    decision_support_status,
                    measurement_status,
                    satellite.get("image_id"),
                    satellite.get("acquisition_time"),
                    payload_json,
                ),
            )
        return {
            "observation_id": observation_id,
            "recorded_at": recorded_at,
            "database": str(self.database_path),
        }

    def list(self, region, limit=50):
        """Return recent observations for one region, including complete payloads."""
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer from 1 to 500")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT observation_id, recorded_at, region, mode, status,
                       satellite_status, identity_status, decision_support_status, measurement_status,
                       image_id, acquisition_time, payload_json
                FROM observations
                WHERE region = ?
                ORDER BY recorded_at DESC
                LIMIT ?
                """,
                (region, limit),
            ).fetchall()
        records = []
        for row in rows:
            record = {
                key: row[key]
                for key in row.keys()
                if key != "payload_json"
            }
            record["observation"] = json.loads(row["payload_json"])
            records.append(record)
        return records

    def get_previous_valid_observation(self, region):
        """Return the newest prior observation with a valid water-area measurement."""
        for record in self.list(region, limit=500):
            observation = record.get("observation") or {}
            satellite = observation.get("satellite") or {}
            water_area = satellite.get("water_area") or {}
            if (
                observation.get("status") == "SUCCESS"
                and observation.get("validity_status") != "UNAVAILABLE"
                and satellite.get("status") == "SUCCESS"
                and water_area.get("status") == "SUCCESS"
                and isinstance(water_area.get("area_sqkm"), (int, float))
            ):
                return record
        return None

    def get_previous_valid_risk_observation(self, region):
        """Return the newest prior observation with a valid risk assessment."""
        for record in self.list(region, limit=500):
            observation = record.get("observation") or {}
            risk = observation.get("risk") or {}
            if (
                observation.get("status") == "SUCCESS"
                and observation.get("validity_status") != "UNAVAILABLE"
                and isinstance(risk.get("risk_score"), (int, float))
                and isinstance(risk.get("risk_level"), str)
            ):
                return record
        return None

    def update_observation_payload(self, observation_id, updates):
        """Merge post-processing fields into an existing observation envelope."""
        if not observation_id or not isinstance(updates, dict):
            raise ValueError("observation_id and updates are required")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"observation not found: {observation_id}")
            payload = json.loads(row["payload_json"])
            payload.update(updates)
            connection.execute(
                "UPDATE observations SET payload_json = ? WHERE observation_id = ?",
                (json.dumps(payload, sort_keys=True, allow_nan=False), observation_id),
            )
            connection.execute(
                """
                UPDATE observations
                SET status = ?,
                    satellite_status = ?,
                    identity_status = ?,
                    decision_support_status = ?,
                    measurement_status = ?
                WHERE observation_id = ?
                """,
                (
                    payload.get("status", "UNKNOWN"),
                    (payload.get("satellite") or {}).get("status"),
                    (payload.get("temporal_evidence") or {}).get("identity_status")
                    or ((payload.get("satellite") or {}).get("candidate_detection") or {}).get("identity_status")
                    or payload.get("identity_status"),
                    (payload.get("decision_support") or {}).get("status"),
                    (payload.get("observed_measurement") or {}).get("status"),
                    observation_id,
                ),
            )

    def save_sensor_telemetry(self, telemetry_result, source_payload=None):
        """Persist one accepted telemetry result without changing observation records."""
        if not isinstance(telemetry_result, dict):
            raise ValueError("telemetry_result must be a dictionary")
        if telemetry_result.get("ingestion_status") != "ACCEPTED":
            raise ValueError("only accepted telemetry can be persisted")

        payload = telemetry_result.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("accepted telemetry payload is required")
        required = ("sensor_id", "region_key", "sensor_type", "timestamp", "reading")
        if any(field not in payload for field in required):
            raise ValueError("accepted telemetry payload is incomplete")
        require_valid_region(payload["region_key"])
        reading = payload["reading"]
        if not isinstance(reading, dict) or "value" not in reading or "unit" not in reading:
            raise ValueError("accepted telemetry reading is incomplete")

        stored_payload = dict(payload)
        if isinstance(source_payload, dict):
            if isinstance(source_payload.get("simulated"), bool):
                stored_payload["simulated"] = source_payload["simulated"]
            if isinstance(source_payload.get("provenance"), (str, dict)):
                stored_payload["provenance"] = source_payload["provenance"]

        sequence = payload.get("sequence")
        if sequence is not None:
            deduplication_key = json.dumps(
                ["sequence", payload["sensor_id"], payload["timestamp"], sequence],
                separators=(",", ":"),
            )
        else:
            deduplication_key = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            )

        telemetry_id = str(uuid.uuid4())
        received_at = telemetry_result.get("received_at")
        if not isinstance(received_at, str):
            raise ValueError("accepted telemetry received_at is required")
        freshness = telemetry_result.get("freshness")
        if not isinstance(freshness, str):
            raise ValueError("accepted telemetry freshness is required")
        provenance = stored_payload.get("provenance")
        provenance_json = (
            json.dumps(provenance, sort_keys=True, allow_nan=False)
            if provenance is not None else None
        )
        simulated = stored_payload.get("simulated")

        with self._connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO sensor_telemetry (
                        telemetry_id, deduplication_key, sensor_id, region_key,
                        sensor_type, telemetry_timestamp, reading_value,
                        reading_unit, sequence, received_at, freshness,
                        simulated, provenance_json, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        telemetry_id,
                        deduplication_key,
                        payload["sensor_id"],
                        payload["region_key"],
                        payload["sensor_type"],
                        payload["timestamp"],
                        reading["value"],
                        reading["unit"],
                        sequence,
                        received_at,
                        freshness,
                        int(simulated) if isinstance(simulated, bool) else None,
                        provenance_json,
                        json.dumps(stored_payload, sort_keys=True, allow_nan=False),
                    ),
                )
            except sqlite3.IntegrityError:
                return {"persisted": False, "duplicate": True}
        return {"persisted": True, "duplicate": False, "telemetry_id": telemetry_id}

    @staticmethod
    def _sensor_row(row):
        payload = json.loads(row["payload_json"])
        return {
            "telemetry_id": row["telemetry_id"],
            "sensor_id": row["sensor_id"],
            "region_key": row["region_key"],
            "sensor_type": row["sensor_type"],
            "timestamp": row["telemetry_timestamp"],
            "reading": {
                "value": row["reading_value"],
                "unit": row["reading_unit"],
            },
            "sequence": row["sequence"],
            "received_at": row["received_at"],
            "freshness": row["freshness"],
            "simulated": bool(row["simulated"]) if row["simulated"] is not None else None,
            "provenance": json.loads(row["provenance_json"])
            if row["provenance_json"] is not None else None,
            "payload": payload,
        }

    def get_latest_sensor_reading(self, sensor_id):
        """Return the latest persisted reading for one sensor, if available."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT telemetry_id, sensor_id, region_key, sensor_type,
                       telemetry_timestamp, reading_value, reading_unit,
                       sequence, received_at, freshness, simulated,
                       provenance_json, payload_json
                FROM sensor_telemetry
                WHERE sensor_id = ?
                ORDER BY telemetry_timestamp DESC, received_at DESC
                LIMIT 1
                """,
                (sensor_id,),
            ).fetchone()
        return self._sensor_row(row) if row else None

    def list_sensor_telemetry(self, region_key, limit=50):
        """Return recent persisted telemetry for one configured region."""
        require_valid_region(region_key)
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer from 1 to 500")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT telemetry_id, sensor_id, region_key, sensor_type,
                       telemetry_timestamp, reading_value, reading_unit,
                       sequence, received_at, freshness, simulated,
                       provenance_json, payload_json
                FROM sensor_telemetry
                WHERE region_key = ?
                ORDER BY telemetry_timestamp DESC, received_at DESC
                LIMIT ?
                """,
                (region_key, limit),
            ).fetchall()
        return [self._sensor_row(row) for row in rows]

    def save_temporal_evidence(self, evidence_run):
        """Persist a complete multi-date evidence run and its source acquisitions."""
        region = require_valid_region(evidence_run.get("region"))
        payload_json = json.dumps(evidence_run, sort_keys=True, allow_nan=False)
        temporal = evidence_run.get("temporal_evidence") or {}
        date_range = evidence_run.get("requested_date_range") or {}
        run_id = str(uuid.uuid4())
        recorded_at = datetime.now(timezone.utc).isoformat()
        observations = evidence_run.get("observations") or []
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO temporal_evidence_runs (
                    run_id, recorded_at, region, status, identity_status,
                    requested_start, requested_end, observation_count, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    recorded_at,
                    region,
                    evidence_run.get("status", "UNKNOWN"),
                    temporal.get("identity_status") or temporal.get("status"),
                    date_range.get("start"),
                    date_range.get("end"),
                    len(observations),
                    payload_json,
                ),
            )
        return {"run_id": run_id, "recorded_at": recorded_at}

    def list_temporal_evidence(self, region, limit=20):
        """Return recent multi-date evidence runs for one region."""
        if not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be an integer from 1 to 200")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT run_id, recorded_at, region, status, identity_status,
                       requested_start, requested_end, observation_count, payload_json
                FROM temporal_evidence_runs
                WHERE region = ?
                ORDER BY recorded_at DESC
                LIMIT ?
                """,
                (region, limit),
            ).fetchall()
        records = []
        for row in rows:
            record = {
                key: row[key]
                for key in row.keys()
                if key != "payload_json"
            }
            record["evidence_run"] = json.loads(row["payload_json"])
            records.append(record)
        return records
