"""Focused tests for automated downstream exposure discovery."""

import json
import os
import tempfile
from unittest.mock import patch

from downstream_impact import build_downstream_impact
from downstream_provider import fetch_automated_downstream_context


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _payload():
    return {
        "elements": [
            {"type": "way", "id": 1, "tags": {"waterway": "river", "name": "Example River"}, "center": {"lat": 27.7, "lon": 86.4}},
            {"type": "node", "id": 2, "tags": {"place": "village", "name": "Example Village", "population": "1200"}, "lat": 27.8, "lon": 86.5},
            {"type": "way", "id": 3, "tags": {"highway": "primary", "name": "Example Road"}, "center": {"lat": 27.9, "lon": 86.6}},
            {"type": "node", "id": 4, "tags": {"amenity": "school", "name": "Example School"}, "lat": 27.9, "lon": 86.6},
        ]
    }


def test_provider_normalizes_osm_context_and_chain():
    with tempfile.TemporaryDirectory() as directory:
        cache_path = os.path.join(directory, "downstream.sqlite3")
        with patch.dict(os.environ, {"G_ALERT_DOWNSTREAM_CACHE_DB": cache_path}):
            with patch("requests.post", return_value=_Response(_payload())):
                context = fetch_automated_downstream_context("test", 27.6, 86.3)
        assert context["status"] == "COMMUNITY_DATA"
        assert len(context["river_or_drainage_path"]) == 1
        assert context["population"]["value"] == 1200
        assert len(context["vulnerable_infrastructure"]) == 2
        chain = build_downstream_impact(
            "test",
            {"lake_name": "Test Lake", "downstream_exposure": {}},
            context,
        )
        assert chain["status"] == "COMMUNITY_DATA"
        assert chain["chain"][1]["status"] == "COMMUNITY_DATA"
        assert chain["chain"][2]["status"] == "COMMUNITY_DATA"
        assert chain["chain"][3]["status"] == "COMMUNITY_DATA"


def test_provider_cache_and_failure_are_graceful():
    with tempfile.TemporaryDirectory() as directory:
        cache_path = os.path.join(directory, "downstream.sqlite3")
        with patch.dict(os.environ, {"G_ALERT_DOWNSTREAM_CACHE_DB": cache_path}):
            with patch("requests.post", return_value=_Response(_payload())) as request:
                fetch_automated_downstream_context("test", 27.6, 86.3)
            with patch("requests.post", side_effect=RuntimeError("network down")) as request:
                cached = fetch_automated_downstream_context("test", 27.6, 86.3)
            assert cached["status"] == "COMMUNITY_DATA"
            assert cached["cache"]["status"] == "HIT"
            assert request.call_count == 0

        with tempfile.TemporaryDirectory() as failure_directory:
            failure_cache = os.path.join(failure_directory, "downstream.sqlite3")
            with patch.dict(os.environ, {"G_ALERT_DOWNSTREAM_CACHE_DB": failure_cache}):
                with patch("requests.post", side_effect=RuntimeError("network down")):
                    failed = fetch_automated_downstream_context("other", 27.6, 86.3)
                assert failed["status"] == "UNAVAILABLE"
                assert failed["river_or_drainage_path"] == []
                assert failed["population"]["value"] is None
                assert failed["limitations"]


if __name__ == "__main__":
    test_provider_normalizes_osm_context_and_chain()
    test_provider_cache_and_failure_are_graceful()
    print("Downstream provider tests: PASS")
