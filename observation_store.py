"""Durable storage for G-ALERT monitoring observation envelopes."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


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
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(observations)")
            }
            if "decision_support_status" not in columns:
                connection.execute(
                    "ALTER TABLE observations ADD COLUMN decision_support_status TEXT"
                )

    def save(self, observation):
        """Persist one complete JSON-safe monitoring result and return its ID."""
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
                    observation.get("region", "UNKNOWN"),
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

    def save_temporal_evidence(self, evidence_run):
        """Persist a complete multi-date evidence run and its source acquisitions."""
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
                    evidence_run.get("region", "UNKNOWN"),
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
