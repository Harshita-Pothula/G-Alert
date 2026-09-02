"""
Interactive Google Earth Engine authentication test.

This script intentionally uses the user-account login flow instead of a
service-account JSON. It does NOT query Sentinel-2 or any other satellite data.
It only verifies that Earth Engine can authenticate and initialize.
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
    print("G-ALERT Earth Engine interactive auth test")
    print("This uses your Google account login flow, not a service-account JSON.")
    print("It does not access Sentinel-2 yet.")

    try:
        print("Open the browser window for Google sign-in if prompted...")
        ee.Authenticate()
        print("Google account authentication step completed.")
    except Exception as exc:
        print(f"ee.Authenticate() raised an exception: {exc}")
        print("This is often harmless if you are already authenticated in the environment.")

    project_id = (
        os.getenv("GEE_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
    )

    try:
        if project_id:
            print(f"Initializing Earth Engine for project: {project_id}")
            ee.Initialize(project=project_id)
        else:
            print("No project ID found in .env (g-alert-507210 / GEE_PROJECT_ID / GOOGLE_CLOUD_PROJECT). Using default EE project config if available.")
            ee.Initialize()

        # A minimal EE call proves the library is initialized correctly.
        value = ee.Number(1).add(1).getInfo()
        print("✅ ee.Initialize() succeeded.")
        print(f"✅ Minimal EE test call returned: {value}")

        if project_id:
            print(f"Connected to G-ALERT Earth Engine project: {project_id}")
        else:
            print("Connected using the default configured Earth Engine project.")

    except Exception as exc:
        print(f"❌ ee.Initialize() failed: {exc}")
        print("If browser login is required, run: earthengine authenticate")
        print("If your project is configured in Google Cloud, set GEE_PROJECT_ID or GOOGLE_CLOUD_PROJECT.")
        raise


if __name__ == "__main__":
    main()
