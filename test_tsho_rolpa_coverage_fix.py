"""
test_tsho_rolpa_coverage_fix.py

Verifies the Sentinel-2 coverage fix for the Tsho Rolpa region:

1. Live monitoring path (run_integrated_monitoring) with the exact date range
   from diag_scl_coverage.py (2026-08-05 .. 2026-09-05) that previously
   selected tile T45RUL — a tile that intersects the search box but has ZERO
   pixels over the lake analysis box (empty SCL histogram, NDWI=null,
   water area 0).

   Expected after fix:
   - The selected image actually covers the analysis box
     (non-empty SCL histogram / valid pixels over the analysis box).
   - NDWI is a real number (not None) and water area is measured.

2. Explicit no-data path: a coverage geometry in an area with no Sentinel-2
   coverage for the window must return NO_SUITABLE_IMAGERY — never
   water_area = 0.

Output -> test_tsho_rolpa_coverage_report.txt
"""

import json
import ee

from main import run_integrated_monitoring
from satellite.gee_pipeline import initialize_gee_pipeline
from satellite.region_config import get_region_bounds, get_region_analysis_bounds
from satellite.ndwi_analysis import NDWIAnalyzer, SCL_CONTAMINATION_CLASSES

out = []


def log(s=""):
    print(s)
    out.append(str(s))


# ---------------------------------------------------------------- Test 1
log("=" * 70)
log("TEST 1: Live monitoring path, Tsho Rolpa, 2026-08-05 .. 2026-09-05")
log("=" * 70)
result = run_integrated_monitoring("Tsho_Rolpa_Nepal", "2026-08-05", "2026-09-05")

log(f"result.status = {result.get('status')}")
sat = result.get("satellite") or {}
log(f"satellite.image_id = {sat.get('image_id')}")
log(f"satellite.ndwi_value = {sat.get('ndwi_value')}")
log(f"satellite.water_area = {json.dumps(sat.get('water_area'))}")
qm = sat.get("quality_masking") or {}
log(f"quality_masking.valid_pixel_fraction = {qm.get('valid_pixel_fraction')}")
log(f"search_metadata.coverage_geometry_verified = "
    f"{(result.get('image_search_metadata') or {}).get('coverage_geometry_verified')}")

# Independent verification: SCL histogram over the analysis box for the
# selected image must be NON-empty (this was the original bug symptom).
analysis = get_region_analysis_bounds("Tsho_Rolpa_Nepal")
pipeline = initialize_gee_pipeline()
selected_image_id = sat.get("image_id")
selected_image = (
    ee.ImageCollection(pipeline.COLLECTION)
    .filter(ee.Filter.eq("system:index", selected_image_id))
    .first()
)
scl_hist = selected_image.select("SCL").reduceRegion(
    reducer=ee.Reducer.frequencyHistogram(), geometry=ee.Geometry(analysis),
    scale=20, maxPixels=10_000_000, bestEffort=True).getInfo()
log(f"independent SCL histogram over analysis box: {json.dumps(scl_hist)}")

test1_pass = (
    result.get("status") == "SUCCESS"
    and isinstance(sat.get("ndwi_value"), (int, float))
    and bool(next(iter(scl_hist.get("SCL", {}).values()), None))
)
log(f"TEST 1 {'PASS' if test1_pass else 'FAIL'}")

# ---------------------------------------------------------------- Test 2
log()
log("=" * 70)
log("TEST 2: Explicit no-data path (coverage geometry with no imagery)")
log("=" * 70)
# A small box far from any land in the requested window: no Sentinel-2 image
# can cover it, so the pipeline must return None (NO_SUITABLE_IMAGERY),
# not an image that would yield water_area = 0.
ocean_box = {
    "type": "Polygon",
    "coordinates": [[
        [-30.0, -30.0], [-29.9, -30.0], [-29.9, -29.9], [-30.0, -29.9], [-30.0, -30.0]
    ]]
}
image2, search2 = pipeline.get_sentinel2_image_with_fallback(
    get_region_bounds("Tsho_Rolpa_Nepal"), "2026-08-05", "2026-09-05",
    cloud_cover_max=20, coverage_geometry=ocean_box, max_window_days=7
)
log(f"image2 = {image2}")
log(f"search2.coverage_geometry_verified = {search2.get('coverage_geometry_verified')}")
log(f"search2.attempts = {len(search2.get('attempts', []))}")

test2_pass = image2 is None and search2.get("coverage_geometry_verified") is True
log(f"TEST 2 {'PASS' if test2_pass else 'FAIL'}")

# ---------------------------------------------------------------- Summary
log()
log("=" * 70)
log(f"OVERALL: {'PASS' if (test1_pass and test2_pass) else 'FAIL'}")
log("=" * 70)

with open("test_tsho_rolpa_coverage_report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\nReport written to test_tsho_rolpa_coverage_report.txt")