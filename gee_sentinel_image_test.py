"""Small test-only Earth Engine image export check.

Uses the existing authenticated GEE setup and the known-good Himalayan test region
and date range. Exports one small RGB Sentinel-2 preview image to the project folder.
"""

import os

from dotenv import load_dotenv

try:
    import ee
except ImportError as exc:
    raise SystemExit("Earth Engine Python package is missing. Run: pip install earthengine-api") from exc


load_dotenv()


TARGET_IMAGE_ID = "20260824T050231_20260824T050638_T45RVM"
OUTPUT_FILE = "gee_sentinel_rgb_test.png"


def main():
    print("GEE Sentinel-2 image export test")
    project_id = os.getenv("GEE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
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
    geometry = ee.Geometry(region)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometry)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )

    image = collection.filter(ee.Filter.eq("system:index", TARGET_IMAGE_ID)).first()
    if image is None:
        print(f"FAIL: image {TARGET_IMAGE_ID} not found in collection.")
        return

    image_id = image.get("system:index").getInfo()
    print(f"selected image ID: {image_id}")

    rgb = image.select(["B4", "B3", "B2"]).visualize(
        min=0,
        max=3000,
        gamma=1.2,
        forceRgbOutput=True
    )

    url = rgb.getThumbURL({
        "region": geometry,
        "dimensions": 512,
        "format": "png"
    })

    print(f"download URL created: {url}")

    try:
        import urllib.request
        urllib.request.urlretrieve(url, OUTPUT_FILE)
        output_path = os.path.abspath(OUTPUT_FILE)
        print(f"output file: {output_path}")
        print("PASS: Sentinel-2 RGB image successfully created.")
    except Exception as exc:
        print(f"FAIL: export/download error: {exc}")


if __name__ == "__main__":
    main()
