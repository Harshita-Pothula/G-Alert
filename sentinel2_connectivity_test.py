"""
Minimal Sentinel-2 connectivity test for G-ALERT.

This is a test script only. It does not modify the main pipeline or NDWI logic.
It verifies that Earth Engine can access Sentinel-2 imagery for one Himalayan region.
"""

from datetime import datetime
from dotenv import load_dotenv

try:
    import ee
except ImportError as exc:
    raise SystemExit(
        "Earth Engine Python package is missing. Run: pip install earthengine-api"
    ) from exc


load_dotenv()


def main() -> None:
    print("G-ALERT Sentinel-2 connectivity test")
    print("This is a minimal test only. No NDWI or main pipeline changes.")

    project_id = None
    try:
        import os
        project_id = os.getenv("GEE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    except Exception:
        project_id = None

    if project_id:
        print(f"Initializing Earth Engine with project: {project_id}")
        ee.Initialize(project=project_id)
    else:
        print("No GEE_PROJECT_ID found. Trying default Earth Engine initialization.")
        ee.Initialize()

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

    print(f"Testing Sentinel-2 imagery for Himalayan region between {start} and {end}")

    geometry = ee.Geometry(region)
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometry)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )

    count = collection.size().getInfo()
    print(f"Sentinel-2 image count in date range: {count}")

    if count > 0:
        image = collection.first()
        metadata = image.getInfo()
        props = metadata.get("properties", {})
        print("✅ Sentinel-2 imagery is available for this region.")
        print(f"First image ID: {props.get('system:index')}")
        print(f"Cloud cover: {props.get('CLOUDY_PIXEL_PERCENTAGE')}%")
    else:
        print("❌ No Sentinel-2 imagery available for this region in the selected date range.")


if __name__ == "__main__":
    main()
