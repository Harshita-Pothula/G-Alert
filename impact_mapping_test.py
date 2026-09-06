"""Focused tests for approximate downstream impact screening."""

from impact_mapping import build_impact_mapping


def _context():
    return {
        "status": "COMMUNITY_DATA",
        "sources": [{"name": "OpenStreetMap", "type": "COMMUNITY_DATA"}],
        "river_or_drainage_path": [
            {"osm_id": "way:1", "name": "Example River", "latitude": 27.61, "longitude": 86.31, "status": "COMMUNITY_DATA"}
        ],
        "settlements": [
            {"osm_id": "node:2", "name": "Example Village", "latitude": 27.62, "longitude": 86.31, "population": 500, "status": "COMMUNITY_DATA"},
            {"osm_id": "node:3", "name": "Far Village", "latitude": 28.5, "longitude": 87.5, "population": 900, "status": "COMMUNITY_DATA"},
        ],
        "vulnerable_infrastructure": [
            {"osm_id": "way:4", "name": "Example Bridge", "asset_type": "bridge", "latitude": 27.62, "longitude": 86.31, "status": "COMMUNITY_DATA"},
        ],
    }


def test_screening_mapping_identifies_nearby_candidates_without_claiming_inundation():
    result = build_impact_mapping(
        "Tsho_Rolpa_Nepal",
        {"lake_name": "Tsho Rolpa", "latitude": 27.6, "longitude": 86.3, "hazard_level": "CRITICAL"},
        _context(),
    )
    assert result["status"] == "SCREENING_APPROXIMATE"
    assert result["classification"] == "SCREENING_APPROXIMATE"
    assert result["corridor"]["directionality"] == "UNVERIFIED"
    assert len(result["exposed_settlements"]) == 1
    assert result["exposed_settlements"][0]["name"] == "Example Village"
    assert result["exposed_infrastructure"][0]["asset_type"] == "bridge"
    assert result["population"]["value"] == 500
    assert any("hydrodynamic" in limitation.lower() for limitation in result["limitations"])


def test_missing_waterways_do_not_become_zero_impact():
    result = build_impact_mapping(
        "Tsho_Rolpa_Nepal",
        {"lake_name": "Tsho Rolpa", "latitude": 27.6, "longitude": 86.3},
        {"status": "UNAVAILABLE", "river_or_drainage_path": [], "settlements": [], "vulnerable_infrastructure": []},
    )
    assert result["status"] == "UNAVAILABLE"
    assert result["corridor"] is None
    assert result["exposed_settlements"] == []
    assert any("do not imply" in limitation for limitation in result["limitations"])


if __name__ == "__main__":
    test_screening_mapping_identifies_nearby_candidates_without_claiming_inundation()
    test_missing_waterways_do_not_become_zero_impact()
    print("Impact mapping tests: PASS")
