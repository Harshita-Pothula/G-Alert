"""Structured downstream-impact context for monitored regions."""


REFERENCE_STATUS = "REFERENCE_CONTEXT"
UNAVAILABLE_STATUS = "UNAVAILABLE"
DOCUMENTED_STATUS = "DOCUMENTED"


def _node(name, value, status, source=None, limitations=None):
    return {
        "name": name,
        "value": value,
        "status": status,
        "source": source,
        "limitations": list(limitations or []),
    }


def build_downstream_impact(region_key, region, automated_context=None):
    """Build a conservative impact chain from the configured region catalog."""
    region = region or {}
    exposure = region.get("downstream_exposure") or {}
    source = exposure.get("reference") or region.get("reference")
    lake_name = region.get("lake_name") or region.get("name")
    population_context = exposure.get("settlements") or exposure.get("population_at_risk") or region.get("population_at_risk")
    automated_context = automated_context or {}
    if automated_context.get("region_key") not in (None, region_key):
        raise ValueError("automated downstream context does not match requested region")
    automated_rivers = automated_context.get("river_or_drainage_path") or []
    automated_settlements = automated_context.get("settlements") or []
    automated_infrastructure = automated_context.get("vulnerable_infrastructure") or []
    automated_population = automated_context.get("population") or {}
    drainage_path = (
        exposure.get("river_or_drainage_path")
        or exposure.get("river")
        or region.get("river_or_drainage_path")
    )
    infrastructure = exposure.get("vulnerable_infrastructure") or region.get("vulnerable_infrastructure")
    if automated_rivers:
        drainage_path = automated_rivers
    if automated_settlements:
        population_context = automated_settlements
    if automated_infrastructure:
        infrastructure = automated_infrastructure
    river_status = "COMMUNITY_DATA" if automated_rivers else REFERENCE_STATUS if drainage_path else UNAVAILABLE_STATUS
    settlement_status = "COMMUNITY_DATA" if automated_settlements else REFERENCE_STATUS if population_context else UNAVAILABLE_STATUS
    infrastructure_status = "COMMUNITY_DATA" if automated_infrastructure else REFERENCE_STATUS if infrastructure else UNAVAILABLE_STATUS

    limitations = [
        "This is catalog/reference context, not a hydrodynamic flood-inundation or travel-time model",
        "Missing downstream data does not mean that no downstream exposure exists",
    ]
    if not drainage_path:
        limitations.append("No verified river or drainage-network path is configured")
    if not infrastructure:
        limitations.append("No verified downstream infrastructure inventory is configured")

    chain = [
        _node(
            "lake",
            lake_name,
            DOCUMENTED_STATUS if lake_name else UNAVAILABLE_STATUS,
            source=source,
            limitations=[] if lake_name else ["Lake name is unavailable"],
        ),
        _node(
            "river_or_drainage_path",
            drainage_path,
            river_status,
            source=(automated_context.get("sources") or [{}])[0].get("name") if automated_rivers else source,
            limitations=[] if drainage_path else ["River/drainage path requires verified catchment or network data"],
        ),
        _node(
            "downstream_settlements",
            population_context,
            settlement_status,
            source=(automated_context.get("sources") or [{}])[0].get("name") if automated_settlements else source,
            limitations=(
                ["Reference context is not a geocoded settlement inventory"]
                if population_context
                else ["No downstream settlement information is configured"]
            ),
        ),
        _node(
            "vulnerable_infrastructure",
            infrastructure,
            infrastructure_status,
            source=(automated_context.get("sources") or [{}])[0].get("name") if automated_infrastructure else source,
            limitations=(
                ["Infrastructure context is not a verified asset inventory"]
                if infrastructure
                else ["No downstream roads, bridges, schools, or hydropower inventory is configured"]
            ),
        ),
    ]
    automated_status = automated_context.get("status")
    result_status = "COMMUNITY_DATA" if automated_status == "COMMUNITY_DATA" else "REFERENCE_CONTEXT" if exposure else "UNAVAILABLE"
    return {
        "region": region_key,
        "status": result_status,
        "chain": chain,
        "downstream_exposure": exposure or None,
        "automated_population": automated_population,
        "automated_provider": {
            "status": automated_status or "NOT_RUN",
            "sources": automated_context.get("sources", []),
            "cache": automated_context.get("cache"),
        },
        "source": source or (automated_context.get("sources") or [{}])[0].get("name"),
        "provenance": {
            "type": result_status,
            "source": source or (automated_context.get("sources") or [{}])[0].get("name"),
            "method": "Configured catalog plus automated global baseline geographic query",
            "limitations": limitations + list(automated_context.get("limitations") or []),
        },
        "limitations": list(dict.fromkeys(limitations + list(automated_context.get("limitations") or []))),
        "interpretation": (
            "Supporting downstream context only; it does not calculate inundation, travel time, or the absence of exposure."
        ),
    }
