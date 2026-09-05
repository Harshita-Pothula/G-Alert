"""
diag_scl_coverage.py - Diagnostic: why did masked Tsho Rolpa give NDWI=null / area=0?

Checks with REAL GEE data:
1. Image footprint vs analysis-box coverage
2. SCL class histogram over the analysis box AND the search box
3. Valid-mask logic sanity (mean of valid mask)
4. UNMASKED vs MASKED NDWI mean and water area (both real measurements)

Output -> diag_scl_report.txt
"""

import json
import ee
from satellite.gee_pipeline import initialize_gee_pipeline
from satellite.region_config import get_region_bounds, get_region_analysis_bounds
from satellite.ndwi_analysis import NDWIAnalyzer, SCL_CONTAMINATION_CLASSES

out = []


def log(s=""):
    print(s)
    out.append(str(s))


pipeline = initialize_gee_pipeline()
region = "Tsho_Rolpa_Nepal"
bounds = get_region_bounds(region)
analysis = get_region_analysis_bounds(region)

image, search = pipeline.get_sentinel2_image_with_fallback(bounds, "2026-08-05", "2026-09-05", 20)
image_id = pipeline.last_metadata["properties"]["system:index"]
log(f"image_id = {image_id}")
log(f"search final_range = {search.get('final_range')}")

# 1. Footprint vs analysis box
fp = image.get("system:footprint").getInfo()
coords = fp.get("coordinates", [[]])[0] if fp.get("type") == "Polygon" else []
if coords:
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    log(f"image footprint lon range: {min(lons) if False else min(lons):.4f} .. {max(lons):.4f}")
    log(f"image footprint lat range: {min(lats):.4f} .. {max(lats):.4f}")
a_coords = analysis["coordinates"][0]
a_lons = [c[0] for c in a_coords]
a_lats = [c[1] for c in a_coords]
log(f"analysis box lon range: {min(a_lons):.4f} .. {max(a_lons):.4f}")
log(f"analysis box lat range: {min(a_lats):.4f} .. {max(a_lats):.4f}")

# 2. SCL histograms (real pixel counts)
scl = image.select("SCL")
hist_analysis = scl.reduceRegion(
    reducer=ee.Reducer.frequencyHistogram(), geometry=ee.Geometry(analysis),
    scale=20, maxPixels=10_000_000, bestEffort=True).getInfo()
log(f"SCL histogram over ANALYSIS box: {json.dumps(hist_analysis)}")
hist_bounds = scl.reduceRegion(
    reducer=ee.Reducer.frequencyHistogram(), geometry=ee.Geometry(bounds),
    scale=100, maxPixels=10_000_000, bestEffort=True).getInfo()
log(f"SCL histogram over SEARCH box (scale 100m): {json.dumps(hist_bounds)}")

# 3. Valid-mask logic sanity
contamination = None
for code in SCL_CONTAMINATION_CLASSES:
    flag = scl.eq(int(code))
    contamination = flag if contamination is None else contamination.Or(flag)
valid = contamination.Not()
valid_mean_analysis = valid.reduceRegion(
    reducer=ee.Reducer.mean(), geometry=ee.Geometry(analysis),
    scale=20, maxPixels=10_000_000, bestEffort=True).getInfo()
log(f"valid-mask mean over analysis box (1=fully valid): {valid_mean_analysis}")

# 4. UNMASKED vs MASKED NDWI + water area (real measurements, both reported)
analyzer = NDWIAnalyzer()
ndwi_raw = analyzer.calculate_ndwi(image)
mask_raw = analyzer.create_water_mask(ndwi_raw)
area_raw = analyzer.calculate_water_area(mask_raw, analysis)
ndwi_raw_mean = ndwi_raw.reduceRegion(
    reducer=ee.Reducer.mean(), geometry=ee.Geometry(analysis),
    scale=30, maxPixels=10_000_000, bestEffort=True).getInfo()
log(f"UNMASKED: ndwi_mean={ndwi_raw_mean}, area={area_raw}")

masked, info = analyzer.apply_quality_mask(image, analysis)
log(f"masking info from apply_quality_mask: {json.dumps(info, indent=2)}")
ndwi_masked = analyzer.calculate_ndwi(masked)
mask_masked = analyzer.create_water_mask(ndwi_masked)
area_masked = analyzer.calculate_water_area(mask_masked, analysis)
ndwi_masked_mean = ndwi_masked.reduceRegion(
    reducer=ee.Reducer.mean(), geometry=ee.Geometry(analysis),
    scale=30, maxPixels=10_000_000, bestEffort=True).getInfo()
log(f"MASKED:   ndwi_mean={ndwi_masked_mean}, area={area_masked}")

with open("diag_scl_report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\nDiag written to diag_scl_report.txt")