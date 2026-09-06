"""
satellite/region_config.py

Configurable Himalayan glacial lake monitoring regions with real, documented lakes.
This module defines where G-ALERT monitors glacial lakes across the Himalayan arc.

Data sources: Wikipedia GLOF documentation, UN monitoring reports, ICIMOD studies.
All coordinates and lake names are from scientific literature.

Lake categories:
- MORAINE_DAMMED: Ice-dammed by terminal moraine (highest GLOF risk)
- ICE_MARGINAL: Dammed by glacier ice (moderate risk)
- PROGLACIAL: At glacier terminus (variable risk)
- GLACIAL_FED: Non-dammed glacial outlet lakes (lower risk)

Note: This is NOT a complete inventory. These are strategically important 
monitoring sites spanning the Himalayan arc from Nepal to Bhutan to Tibet/China.
"""

# Himalayan glacial lake regions for monitoring
# Real documented lakes from scientific literature
# Format: {region_key: {detailed metadata}}

HIMALAYAN_REGIONS = {

    "Langtang_Nepal": {
        "name": "Langtang Valley Glacial Lakes (Nepal)",
        "lake_id": "langtang_glacial_lakes",
        "country": "Nepal",
        "latitude": 28.21,
        "longitude": 85.55,
        "elevation_m": 4500,
        "lake_name": "Langtang Valley glacial lakes",
        "glacier_source": "Langtang Valley glaciers",
        "lake_type": "PROGLACIAL",
        "description": "Representative monitoring region for documented glacial lakes in the Langtang Valley.",
        "hazard_level": "HIGH",
        "reference": "ICIMOD Himalayan glacial lake inventories"
        ,"geometry_status": "APPROXIMATE"
        ,"geometry_source": "Regional center and analysis buffer; authoritative lake polygon not bundled"
    },
    
    # ========== NEPAL ==========
    # Nepal has highest documented GLOF risk in Himalayas
    
    "Tsho_Rolpa_Nepal": {
        "name": "Tsho Rolpa (Nepal) - Rolwaling Valley",
        "lake_id": "tsho_rolpa",
        "country": "Nepal",
        "latitude": 27.6,
        "longitude": 86.3,
        "elevation_m": 4580,
        "lake_name": "Tsho Rolpa",
        "glacier_source": "Trakarding Glacier",
        "lake_type": "MORAINE_DAMMED",
        "description": "One of Nepal's largest and most dangerous glacial lakes. 90-100 million m³ of water. Growing annually due to glacier retreat.",
        "hazard_level": "CRITICAL",
        "moraine_dam_height_m": 150,
        "volume_million_m3": 95,
        "area_sqkm": 1.5,
        "documented_glof_history": "Multiple small outbursts; potential for catastrophic failure",
        "population_at_risk": "Downstream communities in Rolwaling Valley and beyond",
        "downstream_exposure": {
            "population_at_risk": "Downstream communities in Rolwaling Valley and beyond",
            "exposure_description": "Documented glacial lake risk affecting downstream communities in Rolwaling Valley and beyond.",
            "reference": "UN GLOF monitoring database; WECS Nepal 1996 report; ICIMOD 2001"
        },
        "reference": "UN GLOF monitoring database; WECS Nepal 1996 report; ICIMOD 2001"
        ,"geometry_status": "APPROXIMATE"
        ,"geometry_source": "ICIMOD 2001 center reference; authoritative lake polygon not bundled"
    },
    
    "Imja_Tsho_Nepal": {
        "name": "Imja Tsho (Nepal) - Mt. Everest Region",
        "lake_id": "imja_tsho",
        "country": "Nepal",
        "latitude": 27.95,
        "longitude": 86.95,
        "elevation_m": 5010,
        "lake_name": "Imja Tsho",
        "glacier_source": "Imja Glacier",
        "lake_type": "MORAINE_DAMMED",
        "description": "High-altitude glacial lake at Mt. Everest base camp region. Rapid expansion over past 50 years due to climate change.",
        "hazard_level": "HIGH",
        "moraine_dam_height_m": 120,
        "volume_million_m3": 45,
        "area_sqkm": 0.8,
        "documented_glof_history": "Identified as dangerous in 1996 WECS assessment",
        "population_at_risk": "Everest trekking communities; downstream Sagarmatha region",
        "downstream_exposure": {
            "population_at_risk": "Everest trekking communities; downstream Sagarmatha region",
            "exposure_description": "Identified as dangerous with downstream exposure reaching Everest trekking communities and Sagarmatha region populations.",
            "reference": "WECS Nepal 1996; ICIMOD 2001; Khumbu Valley monitoring"
        },
        "reference": "WECS Nepal 1996; ICIMOD 2001; Khumbu Valley monitoring"
        ,"geometry_status": "APPROXIMATE"
        ,"geometry_source": "NASA Earth Observatory 2016 / ICIMOD center reference; authoritative lake polygon not bundled"
    },
    
    "Dig_Tsho_Nepal": {
        "name": "Dig Tsho (Nepal) - Langmale Valley",
        "lake_id": "dig_tsho",
        "country": "Nepal",
        "latitude": 27.72,
        "longitude": 86.50,
        "elevation_m": 4350,
        "lake_name": "Dig Tsho",
        "glacier_source": "Langmale Glacier",
        "lake_type": "MORAINE_DAMMED",
        "description": "Site of major 1985 glacial lake outburst flood. Regenerating after event. Important for GLOF understanding.",
        "hazard_level": "HIGH",
        "moraine_dam_height_m": 100,
        "volume_million_m3": 25,
        "area_sqkm": 0.5,
        "documented_glof_history": "1985 GLOF event triggered detailed GLOF research globally",
        "population_at_risk": "Downstream communities in Dudh Kosi river valley",
        "downstream_exposure": {
            "population_at_risk": "Downstream communities in Dudh Kosi river valley",
            "exposure_description": "Historic GLOF event documented with downstream exposure in the Dudh Kosi river valley.",
            "reference": "Historic 1985 GLOF; Nepal disaster records"
        },
        "reference": "Historic 1985 GLOF; Nepal disaster records"
        ,"geometry_status": "APPROXIMATE"
        ,"geometry_source": "Regional center and analysis buffer; authoritative lake polygon not bundled"
    },
    
    "Thulagi_Nepal": {
        "name": "Thulagi (Nepal) - Upper Marsyangdi Basin",
        "lake_id": "thulagi",
        "country": "Nepal",
        "latitude": 28.50,
        "longitude": 84.40,
        "elevation_m": 4200,
        "lake_name": "Thulagi",
        "glacier_source": "Thulagi Glacier",
        "lake_type": "MORAINE_DAMMED",
        "description": "Supra-glacial lake in Upper Marsyangdi River basin. One of two identified moraine-dammed supra-glacial lakes in Nepal.",
        "hazard_level": "MODERATE",
        "moraine_dam_height_m": 80,
        "volume_million_m3": 15,
        "area_sqkm": 0.3,
        "documented_glof_history": "Identified as potentially dangerous. 2011 BGR study concluded imminent catastrophic outburst unlikely.",
        "population_at_risk": "Upper Marsyangdi valley communities",
        "downstream_exposure": {
            "population_at_risk": "Upper Marsyangdi valley communities",
            "exposure_description": "Potential downstream impact on Upper Marsyangdi valley communities documented in regional monitoring studies.",
            "reference": "BGR/NLfB/GGA 2011 study; ICIMOD 2001"
        },
        "reference": "BGR/NLfB/GGA 2011 study; ICIMOD 2001"
        ,"geometry_status": "APPROXIMATE"
        ,"geometry_source": "Regional center and analysis buffer; authoritative lake polygon not bundled"
    },
    
    # ========== BHUTAN ==========
    # Bhutan has ~2674 glacial lakes; 24 identified as GLOF candidates
    
    "Thorthormi_Bhutan": {
        "name": "Thorthormi (Bhutan) - Pho Chu Basin",
        "lake_id": "thorthormi",
        "country": "Bhutan",
        "latitude": 27.85,
        "longitude": 89.90,
        "elevation_m": 4520,
        "lake_name": "Thorthormi",
        "glacier_source": "Thorthormi Glacier",
        "lake_type": "ICE_MARGINAL",
        "description": "Threatened imminent catastrophic collapse in 2001. Water channel carved to relieve pressure.",
        "hazard_level": "CRITICAL",
        "moraine_dam_height_m": 140,
        "volume_million_m3": 40,
        "area_sqkm": 0.7,
        "documented_glof_history": "2001 emergency intervention to prevent catastrophic failure",
        "population_at_risk": "Pho Chu River valley; Punakha region downstream",
        "downstream_exposure": {
            "population_at_risk": "Pho Chu River valley; Punakha region downstream",
            "exposure_description": "Emergency intervention and documented downstream risk to the Pho Chu River valley and Punakha region.",
            "reference": "2001 emergency intervention; Bhutan GLOF study"
        },
        "reference": "2001 emergency intervention; Bhutan GLOF study"
        ,"geometry_status": "APPROXIMATE"
        ,"geometry_source": "Bhutan GLOF study center reference; authoritative lake polygon not bundled"
    },
    
    "Raphstreng_Tsho_Bhutan": {
        "name": "Raphstreng Tsho (Bhutan) - Thimphu Valley",
        "lake_id": "raphstreng",
        "country": "Bhutan",
        "latitude": 27.60,
        "longitude": 89.60,
        "elevation_m": 4180,
        "lake_name": "Raphstreng Tsho",
        "glacier_source": "Raphstreng Glacier",
        "lake_type": "MORAINE_DAMMED",
        "description": "Glacial lake in region with regular GLOF occurrence. Bhutan experiences GLOFs with regularity in valleys.",
        "hazard_level": "HIGH",
        "moraine_dam_height_m": 110,
        "volume_million_m3": 30,
        "area_sqkm": 0.6,
        "documented_glof_history": "Flash floods occur regularly in Bhutan valleys",
        "population_at_risk": "Thimphu valley; major population centers",
        "downstream_exposure": {
            "population_at_risk": "Thimphu valley; major population centers",
            "exposure_description": "Regular valley flood activity with downstream exposure affecting Thimphu valley and major population centers.",
            "reference": "Bhutan glacial hazards study; 2674 lakes inventory"
        },
        "reference": "Bhutan glacial hazards study; 2674 lakes inventory"
        ,"geometry_status": "APPROXIMATE"
        ,"geometry_source": "Regional center and analysis buffer; authoritative lake polygon not bundled"
    },
    
    # ========== TIBET / CHINA ==========
    # Eastern Himalayas with high GLOF risk
    
    "Longbasaba_Pida_Tibet": {
        "name": "Longbasaba & Pida Lakes (Tibet) - Eastern Himalayas",
        "lake_id": "longbasaba_pida",
        "country": "China (Tibet)",
        "latitude": 30.35,
        "longitude": 90.50,
        "elevation_m": 5700,
        "lake_name": "Longbasaba & Pida",
        "glacier_source": "Longbasaba & Kaer Glaciers",
        "lake_type": "MORAINE_DAMMED",
        "description": "Two moraine-dammed lakes at ~5700m. Glacier areas decreased 8.7% and 16.6% (1978-2005). Lake areas increased 140% and 194%.",
        "hazard_level": "CRITICAL",
        "moraine_dam_height_m": 160,
        "volume_million_m3": 200,
        "area_sqkm": 3.5,
        "documented_glof_history": "If GLOF occurs: 23 towns/villages endangered; 12,500+ people at risk",
        "population_at_risk": "23 towns and villages; significant population center in Tibet",
        "downstream_exposure": {
            "population_at_risk": "23 towns and villages; significant population center in Tibet",
            "exposure_description": "Documented downstream risk to 23 towns and villages and a significant population center in Tibet if a GLOF occurs.",
            "reference": "Tibet Hydrological Department 2006; Wang et al. 2008 study"
        },
        "reference": "Tibet Hydrological Department 2006; Wang et al. 2008 study"
        ,"geometry_status": "APPROXIMATE"
        ,"geometry_source": "Wang et al. 2008 center reference; authoritative lake polygon not bundled"
    },
    
    "Shaksgam_Karakoram": {
        "name": "Shaksgam Glacial Lakes (Karakoram-Himalayan Boundary)",
        "lake_id": "shaksgam",
        "country": "China-Pakistan boundary",
        "latitude": 35.20,
        "longitude": 77.00,
        "elevation_m": 5200,
        "lake_name": "Shaksgam Valley Glacial Lakes",
        "glacier_source": "Multiple Karakoram glaciers",
        "lake_type": "MORAINE_DAMMED",
        "description": "Major GLOF in 1929 at Chong Khumdan Glacier affected Indus River 1,200 km downstream.",
        "hazard_level": "CRITICAL",
        "moraine_dam_height_m": 150,
        "volume_million_m3": 150,
        "area_sqkm": 2.5,
        "documented_glof_history": "1929 GLOF: 1,200 km downstream impact on Indus River; 8.1 m flood rise at Attock",
        "population_at_risk": "Indus River downstream communities in Pakistan",
        "downstream_exposure": {
            "population_at_risk": "Indus River downstream communities in Pakistan",
            "exposure_description": "Historical GLOF impact extending 1,200 km downstream along the Indus River to downstream communities in Pakistan.",
            "reference": "Hewitt 1982; USGS historical records; Karakoram monitoring"
        },
        "reference": "Hewitt 1982; USGS historical records; Karakoram monitoring"
        ,"geometry_status": "APPROXIMATE"
        ,"geometry_source": "Regional center and analysis buffer; authoritative lake polygon not bundled"
    },
    
    # ========== INDIA (HIMALAYAN STATES) ==========
    
    "Chorabari_Tal_India": {
        "name": "Chorabari Tal (India) - Uttarakhand, Kedarnath Region",
        "lake_id": "chorabari_tal",
        "country": "India",
        "latitude": 30.75,
        "longitude": 79.18,
        "elevation_m": 3880,
        "lake_name": "Chorabari Tal (Chorabari Glacier Lake)",
        "glacier_source": "Chorabari Glacier",
        "lake_type": "PROGLACIAL",
        "description": "Site of June 2013 disaster. Glacial lake outburst combined with weather-triggered flash flood.",
        "hazard_level": "CRITICAL",
        "moraine_dam_height_m": 90,
        "volume_million_m3": 18,
        "area_sqkm": 0.4,
        "documented_glof_history": "June 2013: GLOF caused thousands of deaths. Major disaster event.",
        "population_at_risk": "Kedarnath Valley; pilgrimage sites; major religious significance",
        "downstream_exposure": {
            "population_at_risk": "Kedarnath Valley; pilgrimage sites; major religious significance",
            "exposure_description": "Major disaster event with downstream exposure affecting Kedarnath Valley, pilgrimage sites, and major religious significance areas.",
            "reference": "2013 North India floods; India disaster records"
        },
        "reference": "2013 North India floods; India disaster records"
        ,"geometry_status": "APPROXIMATE"
        ,"geometry_source": "Regional center and analysis buffer; authoritative lake polygon not bundled"
    }
}

# Categorization for analysis
GLACIAL_LAKE_CATEGORIES = {
    "MORAINE_DAMMED": {
        "risk_level": "CRITICAL",
        "description": "Dammed by unconsolidated terminal moraine. Highest GLOF risk.",
        "characteristics": ["Unstable dam", "Rapid water accumulation", "Potential for catastrophic failure"]
    },
    "ICE_MARGINAL": {
        "risk_level": "HIGH",
        "description": "Dammed by glacier ice. Moderate GLOF risk.",
        "characteristics": ["Ice dam can fail", "Calving hazard", "Outflow instability"]
    },
    "PROGLACIAL": {
        "risk_level": "MODERATE",
        "description": "At glacier terminus. Variable GLOF risk.",
        "characteristics": ["Outflow channel present", "Can be sudden", "Often linked to other hazards"]
    },
    "GLACIAL_FED": {
        "risk_level": "LOW",
        "description": "Glacial-fed but not dammed by ice/moraine.",
        "characteristics": ["Regulated outflow", "Lower catastrophic risk", "Important for monitoring"]
    }
}

def get_region_bounds(region_key):
    """
    Get bounding box geometry for GEE satellite queries.
    
    Args:
        region_key: Key from HIMALAYAN_REGIONS dict
        
    Returns:
        GeoJSON Polygon geometry for Google Earth Engine
    """
    
    region = HIMALAYAN_REGIONS.get(region_key)
    if not region:
        return None
    
    lat = region["latitude"]
    lon = region["longitude"]
    
    # Adaptive buffer based on region size and hazard
    # GLOF-critical regions: larger buffer for comprehensive monitoring
    hazard_buffers = {
        "CRITICAL": 0.35,    # ~35km radius (~70km x 70km area)
        "HIGH": 0.25,        # ~25km radius (~50km x 50km area)
        "MODERATE": 0.15     # ~15km radius (~30km x 30km area)
    }
    
    hazard = region.get("hazard_level", "MODERATE")
    buffer = hazard_buffers.get(hazard, 0.15)
    
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - buffer, lat - buffer],
            [lon + buffer, lat - buffer],
            [lon + buffer, lat + buffer],
            [lon - buffer, lat + buffer],
            [lon - buffer, lat - buffer]
        ]],
        "properties": {
            "region_key": region_key,
            "buffer_degrees": buffer,
            "hazard_level": hazard
        }
    }

def get_region_analysis_bounds(region_key):
    region = HIMALAYAN_REGIONS.get(region_key)
    if not region:
        return None

    # Use lake-specific coordinates for analysis where available from scientific literature.
    # Keep the main region coordinates unchanged for Sentinel-2 search.
    # Sources: ICIMOD studies, WECS Nepal reports, published glacial lake inventories
    analysis_centers = {
        "Tsho_Rolpa_Nepal": {
            "latitude": 27.861,
            "longitude": 86.476,
            "buffer": 0.02,
            "source": "ICIMOD 2001 glacial lake inventory"
        },
        "Imja_Tsho_Nepal": {
            "latitude": 27.934,
            "longitude": 86.926,
            "buffer": 0.015,
            "source": "NASA Earth Observatory 2016, ICIMOD monitoring"
        },
        "Thorthormi_Bhutan": {
            "latitude": 27.833,
            "longitude": 89.883,
            "buffer": 0.015,
            "source": "Bhutan GLOF study 2001, ICIMOD 2009"
        },
        "Longbasaba_Pida_Tibet": {
            "latitude": 30.317,
            "longitude": 90.467,
            "buffer": 0.02,
            "source": "Wang et al. 2008, Tibet Hydrological Department 2006"
        }
    }

    if region_key in analysis_centers:
        center = analysis_centers[region_key]
        lat = center["latitude"]
        lon = center["longitude"]
        analysis_buffer = center["buffer"]
        has_lake_specific_coords = True
        coord_source = center["source"]
    else:
        lat = region["latitude"]
        lon = region["longitude"]
        analysis_buffer = 0.03
        has_lake_specific_coords = False
        coord_source = "Regional center point (not lake-specific)"

    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - analysis_buffer, lat - analysis_buffer],
            [lon + analysis_buffer, lat - analysis_buffer],
            [lon + analysis_buffer, lat + analysis_buffer],
            [lon - analysis_buffer, lat + analysis_buffer],
            [lon - analysis_buffer, lat - analysis_buffer]
        ]],
        "properties": {
            "has_lake_specific_coords": has_lake_specific_coords,
            "coord_source": coord_source,
            "analysis_buffer_degrees": analysis_buffer
        }
    }    


def get_lake_geometry(region_key):
    """Return the best configured geometry without upgrading its trust level."""
    region = HIMALAYAN_REGIONS.get(region_key)
    if not region:
        return None, {"status": "UNKNOWN", "source": None, "geometry_type": "NONE"}

    configured_geometry = region.get("lake_geometry")
    if configured_geometry is not None:
        return configured_geometry, {
            "status": region.get("geometry_status", "UNKNOWN"),
            "source": region.get("geometry_source"),
            "geometry_type": "LAKE_POLYGON",
        }

    return get_region_analysis_bounds(region_key), {
        "status": region.get("geometry_status", "UNKNOWN"),
        "source": region.get("geometry_source"),
        "geometry_type": "APPROXIMATE_ANALYSIS_ROI",
    }


def get_authoritative_reference(region_key):
    """Return an optional trusted reference geometry without inventing one."""
    region = HIMALAYAN_REGIONS.get(region_key)
    if not region:
        return None, {
            "status": "UNAVAILABLE",
            "trust_status": "UNTRUSTED",
            "source": None,
        }
    geometry = region.get("authoritative_geometry")
    metadata = region.get("authoritative_geometry_metadata")
    if not isinstance(geometry, dict) or not isinstance(metadata, dict):
        return None, {
            "status": "UNAVAILABLE",
            "trust_status": "UNTRUSTED",
            "source": None,
            "reason": "No verified authoritative reference geometry is configured",
        }
    return geometry, metadata

def get_all_regions():
    """Return all available monitoring regions."""
    return HIMALAYAN_REGIONS

def get_region_info(region_key):
    """Get detailed info about a specific region."""
    return HIMALAYAN_REGIONS.get(region_key)

def get_regions_by_country(country_name):
    """
    Get all monitoring regions in a specific country.
    
    Args:
        country_name: Country name ("Nepal", "Bhutan", "India", "China (Tibet)", etc.)
        
    Returns:
        dict of regions in that country
    """
    
    return {
        key: region 
        for key, region in HIMALAYAN_REGIONS.items()
        if region.get("country") == country_name
    }

def get_regions_by_hazard_level(hazard_level):
    """
    Get all regions above a certain hazard threshold.
    
    Args:
        hazard_level: "CRITICAL", "HIGH", "MODERATE"
        
    Returns:
        dict of matching regions
    """
    
    hazard_order = {"CRITICAL": 3, "HIGH": 2, "MODERATE": 1}
    target_level = hazard_order.get(hazard_level, 0)
    
    return {
        key: region
        for key, region in HIMALAYAN_REGIONS.items()
        if hazard_order.get(region.get("hazard_level"), 0) >= target_level
    }

def get_lake_type_info(lake_type):
    """Get information about a specific lake category."""
    return GLACIAL_LAKE_CATEGORIES.get(lake_type)

def list_all_lake_types():
    """List all available lake types with risk levels."""
    return {
        lake_type: info["risk_level"]
        for lake_type, info in GLACIAL_LAKE_CATEGORIES.items()
    }

def validate_region_key(region_key):
    """Check if a region key is valid."""
    return region_key in HIMALAYAN_REGIONS

def get_monitoring_metadata():
    """
    Get metadata about the monitoring network.
    
    Returns:
        dict with network-wide statistics
    """
    
    regions = HIMALAYAN_REGIONS
    numeric_population_values = [
        region.get("population_at_risk")
        for region in regions.values()
        if isinstance(region.get("population_at_risk"), int)
        and region.get("population_at_risk") >= 0
    ]
    
    return {
        "total_regions": len(regions),
        "countries_covered": list(set(r["country"] for r in regions.values())),
        "critical_sites": len([r for r in regions.values() if r.get("hazard_level") == "CRITICAL"]),
        "high_risk_sites": len([r for r in regions.values() if r.get("hazard_level") == "HIGH"]),
        "total_people_at_risk": sum(numeric_population_values) if numeric_population_values else None,
        "reference_sources": [
            "UN GLOF monitoring database",
            "WECS Nepal reports",
            "ICIMOD studies",
            "BGR/NLfB/GGA research",
            "Historic disaster records",
            "Wikipedia GLOF documentation"
        ],
        "disclaimer": "All lakes are REAL and documented in scientific literature. This is NOT a complete inventory."
    }

