"""
satellite/gee_pipeline.py

Google Earth Engine authentication and Sentinel-2 data retrieval pipeline.
Handles connection to GEE and satellite imagery processing.
"""

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Import Earth Engine
try:
    import ee
except ImportError:
    print("ERROR: earthengine-api not installed. Run: pip install earthengine-api")
    ee = None

load_dotenv()

class GEEAuthenticator:
    """Handles Google Earth Engine authentication."""
    
    def __init__(self, credentials_path=None):
        """
        Initialize GEE authenticator.
        
        Args:
            credentials_path: Path to GEE service account JSON (optional)
        """
        if ee is None:
            raise RuntimeError("Earth Engine API not available")
        
        self.credentials_path = credentials_path or os.getenv("GEE_CREDENTIALS_PATH")
        self.authenticated = False
    
    def authenticate(self):
        """
        Authenticate with Google Earth Engine.
        
        Two methods:
        1. Service account (for headless/backend use) - preferred for hackathon
        2. User account (interactive browser login)
        """
        try:
            project_id = os.getenv("GEE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
            if self.credentials_path and os.path.exists(self.credentials_path):
                # Service account authentication
                ee.Initialize(
                    ee.ServiceAccountCredentials(
                        email=None,
                        key_file=self.credentials_path
                    ),
                    project=project_id
                )
                print(f"✓ GEE authenticated via service account: {self.credentials_path}")
            else:
                # User authentication (opens browser)
                ee.Initialize(project=project_id) if project_id else ee.Initialize()
                print("✓ GEE authenticated via user account")
            
            self.authenticated = True
            return True
            
        except Exception as e:
            print(f"✗ GEE authentication failed: {e}")
            print("  Download service account JSON from: https://console.cloud.google.com/")
            print("  Or run: earthengine authenticate")
            return False
    
    def is_authenticated(self):
        """Check if authentication is successful."""
        return self.authenticated


class Sentinel2Pipeline:
    """Retrieves and processes Sentinel-2 satellite imagery."""
    
    # Sentinel-2 Surface Reflectance Harmonized collection
    COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
    
    # Sentinel-2 band names
    BANDS = {
        "BLUE": "B2",
        "GREEN": "B3",
        "RED": "B4",
        "NIR": "B8",
        "SWIR": "B11"
    }
    
    def __init__(self, authenticator):
        """
        Initialize Sentinel-2 pipeline.
        
        Args:
            authenticator: GEEAuthenticator instance (must be authenticated)
        """
        if not authenticator.is_authenticated():
            raise RuntimeError("GEE not authenticated")
        
        self.authenticator = authenticator
        self.last_image = None
        self.last_metadata = None
    
    def get_sentinel2_image(self, region_geometry, start_date, end_date, cloud_cover_max=20):
        """
        Retrieve Sentinel-2 image for a region and date range.
        
        Args:
            region_geometry: GeoJSON polygon for region of interest
            start_date: Start date (string "YYYY-MM-DD" or datetime)
            end_date: End date (string "YYYY-MM-DD" or datetime)
            cloud_cover_max: Maximum cloud cover percentage (default 20%)
            
        Returns:
            ee.Image object or None if no suitable image found
        """
        
        try:
            self.last_image = None
            self.last_metadata = None
            # Convert strings to datetime if needed
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d")
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, "%Y-%m-%d")
            
            # Create EE geometry
            ee_geometry = ee.Geometry(region_geometry)
            
            # Filter image collection
            collection = (
                ee.ImageCollection(self.COLLECTION)
                .filterBounds(ee_geometry)
                .filterDate(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_cover_max))
                .sort("CLOUDY_PIXEL_PERCENTAGE")
            )
            
            # Validate the server-side collection before selecting an image.
            if collection.size().getInfo() == 0:
                print(f"✗ No Sentinel-2 images found for date range {start_date.date()} to {end_date.date()}")
                return None

            # Get first (least cloudy) image
            image = collection.first()
            
            # Get metadata
            metadata = image.getInfo()
            self.last_image = image
            self.last_metadata = metadata
            
            print(f"✓ Retrieved Sentinel-2 image from {metadata['properties']['system:index']}")
            print(f"  Cloud cover: {metadata['properties']['CLOUDY_PIXEL_PERCENTAGE']}%")
            
            return image
            
        except Exception as e:
            print(f"✗ Error retrieving Sentinel-2 image: {e}")
            return None
    
    def download_image_data(self, image, region_geometry, scale=30):
        """
        Download image data for analysis.
        
        Args:
            image: ee.Image object
            region_geometry: GeoJSON polygon
            scale: Pixel scale in meters (default 30m for Sentinel-2)
            
        Returns:
            dict with image data and metadata
        """
        
        try:
            ee_geometry = ee.Geometry(region_geometry)
            
            # Get image information
            image_data = image.reduceRegion(
                reducer=ee.Reducer.first(),
                geometry=ee_geometry,
                scale=scale
            ).getInfo()
            
            return {
                "status": "success",
                "data": image_data,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"✗ Error downloading image data: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_band_values(self, image, band_name, region_geometry, scale=30):
        """
        Extract specific band values from image.
        
        Args:
            image: ee.Image object
            band_name: Band name from BANDS dict
            region_geometry: GeoJSON polygon
            scale: Pixel scale in meters
            
        Returns:
            Band data or None
        """
        
        try:
            if band_name not in self.BANDS:
                print(f"✗ Unknown band: {band_name}")
                return None
            
            band = self.BANDS[band_name]
            ee_geometry = ee.Geometry(region_geometry)
            
            # Extract band
            band_image = image.select(band)
            
            # Get statistics
            stats = band_image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_geometry,
                scale=scale
            ).getInfo()
            
            return stats
            
        except Exception as e:
            print(f"✗ Error extracting band {band_name}: {e}")
            return None


def initialize_gee_pipeline(credentials_path=None):
    """
    Initialize complete GEE pipeline for satellite data retrieval.
    
    Args:
        credentials_path: Optional path to GEE service account JSON
        
    Returns:
        Sentinel2Pipeline instance if successful, None otherwise
    """
    
    print("\n=== Initializing G-ALERT Satellite Pipeline ===")
    print("Connecting to Google Earth Engine...")
    
    # Authenticate
    authenticator = GEEAuthenticator(credentials_path)
    if not authenticator.authenticate():
        return None
    
    # Initialize pipeline
    try:
        pipeline = Sentinel2Pipeline(authenticator)
        print("✓ Satellite pipeline ready\n")
        return pipeline
    except Exception as e:
        print(f"✗ Failed to initialize pipeline: {e}")
        return None
