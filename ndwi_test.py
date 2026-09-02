"""
NDWI test-only script for G-ALERT.

This script uses verified Earth Engine user authentication and a real Sentinel-2
image from the COPERNICUS/S2_SR_HARMONIZED collection. It does not modify any
existing project files or connect to the risk engine.
"""

import os
from dotenv import load_dotenv

try:
    import ee
except ImportError as exc:
    raise SystemExit(
        "Earth Engine Python package is missing. Run: pip install earthengine-api"
    ) from exc


load_dotenv()


def main() -> None:
    print("G-ALERT NDWI test")
    print("This is a test only. No production files are modified.")

    project_id = os.getenv("GEE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if project_id:
        print(f"Initializing Earth Engine with project: {project_id}")
        ee.Initialize(project=project_id)
    else:
        print("No GEE_PROJECT_ID found. Trying default Earth Engine initialization.")
        ee.Initialize()

    # Use the same region geometry from the successful Sentinel-2 connectivity test.
    region = {
        "type": "Polygon",
        "coordinates": [[
            [86.0, 27.0],
            [86.0, 28.5],
            [87.5, 28.5],
            [87.5, 27.0],
            [86.0, 27.0]
        ]]
    }

    start = "2026-08-20"
    end = "2026-08-30"
    geometry = ee.Geometry(region)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometry)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )

    image_count = collection.size().getInfo()
    print(f"Collection count: {image_count}")

    if image_count == 0:
        print("❌ No Sentinel-2 imagery available for the selected date range and region.")
        return

    target_image_id = "20260824T050231_20260824T050638_T45RVM"
    image = collection.filter(ee.Filter.eq("system:index", target_image_id)).first()

    if image is None:
        print(f"⚠️ Exact image ID {target_image_id} not found in the filtered collection.")
        image = collection.first()
        print("Using the first available image instead.")

    image_id = image.id().getInfo() if hasattr(image, "id") else None
    if image_id:
        print(f"Selected image ID: {image_id}")
    else:
        print("Selected image ID: unavailable")

    green = image.select("B3")
    nir = image.select("B8")
    ndwi = green.subtract(nir).divide(green.add(nir))

    ndwi_mean = ndwi.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=30,
        maxPixels=1e13,
        bestEffort=True
    ).getInfo()

    mean_ndwi = ndwi_mean.get("B3")
    print(f"NDWI calculation status: success")
    print(f"Mean NDWI over test region: {mean_ndwi}")

    water_mask = ndwi.gt(0.3).selfMask()
    water_area_result = water_mask.multiply(ee.Image.pixelArea()).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry,
        scale=30,
        maxPixels=1e13,
        bestEffort=True
    ).getInfo()

    if not water_area_result:
        area_sq_m = 0
        print("Estimated water area: 0 sq m")
    else:
        area_sq_m = float(water_area_result.get("constant", 0) or 0)
        print(f"Estimated water area: {area_sq_m} sq m")


if __name__ == "__main__":
    main()
