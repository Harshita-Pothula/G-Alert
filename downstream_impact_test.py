"""Focused tests for downstream impact context."""

from downstream_impact import build_downstream_impact


def test_reference_downstream_chain_preserves_catalog_context():
    region = {
        "lake_name": "Example Lake",
        "reference": "Regional study",
        "downstream_exposure": {
            "population_at_risk": "Valley settlements",
            "reference": "Regional exposure assessment",
        },
    }
    result = build_downstream_impact("example", region)
    assert result["status"] == "REFERENCE_CONTEXT"
    assert [node["name"] for node in result["chain"]] == [
        "lake",
        "river_or_drainage_path",
        "downstream_settlements",
        "vulnerable_infrastructure",
    ]
    assert result["chain"][0]["status"] == "DOCUMENTED"
    assert result["chain"][2]["value"] == "Valley settlements"
    assert result["chain"][2]["status"] == "REFERENCE_CONTEXT"
    assert result["chain"][1]["status"] == "UNAVAILABLE"
    assert result["chain"][3]["status"] == "UNAVAILABLE"
    assert any("does not mean" in item for item in result["limitations"])


def test_configured_river_and_infrastructure_are_exposed_without_inference():
    region = {
        "lake_name": "Mapped Lake",
        "downstream_exposure": {
            "river_or_drainage_path": "Example River",
            "settlements": ["Example Town"],
            "vulnerable_infrastructure": ["Example bridge"],
            "reference": "Verified basin inventory",
        },
    }
    result = build_downstream_impact("mapped", region)
    assert result["chain"][1]["value"] == "Example River"
    assert result["chain"][1]["status"] == "REFERENCE_CONTEXT"
    assert result["chain"][2]["value"] == ["Example Town"]
    assert result["chain"][3]["value"] == ["Example bridge"]


if __name__ == "__main__":
    test_reference_downstream_chain_preserves_catalog_context()
    test_configured_river_and_infrastructure_are_exposed_without_inference()
    print("Downstream impact tests: PASS")
