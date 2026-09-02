"""
satellite/ndwi_analysis.py

Normalized Difference Water Index (NDWI) calculation for water/lake detection.
NDWI = (Green - NIR) / (Green + NIR)

For Sentinel-2:
- Green = B3
- NIR = B8
"""

import numpy as np
from datetime import datetime
import json

# Import Earth Engine
try:
    import ee
except ImportError:
    print("ERROR: earthengine-api not installed. Run: pip install earthengine-api")
    ee = None

class NDWIAnalyzer:
    """Calculates NDWI and performs water detection."""
    
    def __init__(self, ndwi_water_threshold=0.3):
        """
        Initialize NDWI analyzer.
        
        Args:
            ndwi_water_threshold: NDWI threshold for water detection
                                 (values > threshold = water)
                                 Default 0.3 is demo threshold
        """
        self.ndwi_water_threshold = ndwi_water_threshold
        self.last_ndwi = None
        self.last_water_mask = None
        self.last_lake_area = None
    
    def calculate_ndwi(self, image_or_bands):
        """
        Calculate NDWI from Sentinel-2 image.
        
        Args:
            image_or_bands: Either:
                - ee.Image object (from GEE pipeline)
                - dict with "GREEN" and "NIR" band values
                
        Returns:
            NDWI values (numpy array or dict)
        """
        
        try:
            # If EE Image object
            if hasattr(image_or_bands, "select"):
                # Extract Green (B3) and NIR (B8)
                green = image_or_bands.select("B3")  # Green
                nir = image_or_bands.select("B8")    # NIR
                
                # NDWI = (Green - NIR) / (Green + NIR)
                ndwi = green.subtract(nir).divide(green.add(nir))
                self.last_ndwi = ndwi
                
                print("✓ NDWI calculated from EE Image")
                return ndwi
            
            # If dict with band values
            elif isinstance(image_or_bands, dict):
                green = image_or_bands.get("GREEN", 0)
                nir = image_or_bands.get("NIR", 0)
                
                # Handle division by zero
                if green + nir == 0:
                    ndwi_value = 0
                else:
                    ndwi_value = (green - nir) / (green + nir)
                
                self.last_ndwi = ndwi_value
                print(f"✓ NDWI calculated: {ndwi_value:.4f}")
                return ndwi_value
            
            else:
                print("✗ Invalid input for NDWI calculation")
                return None
                
        except Exception as e:
            print(f"✗ Error calculating NDWI: {e}")
            return None
    
    def create_water_mask(self, ndwi_image, threshold=None):
        """
        Create binary water mask from NDWI.
        
        Args:
            ndwi_image: NDWI values
            threshold: Water detection threshold (uses default if None)
            
        Returns:
            Binary water mask (1 = water, 0 = no water)
        """
        
        try:
            if threshold is None:
                threshold = self.ndwi_water_threshold
            
            # If EE Image
            if hasattr(ndwi_image, "select"):
                water_mask = ndwi_image.gt(threshold).selfMask()
                self.last_water_mask = water_mask
                print(f"✓ Water mask created (threshold: {threshold})")
                return water_mask
            
            # If numeric
            elif isinstance(ndwi_image, (int, float)):
                water_mask = 1 if ndwi_image > threshold else 0
                self.last_water_mask = water_mask
                print(f"✓ Water mask: {water_mask} (NDWI: {ndwi_image:.4f}, threshold: {threshold})")
                return water_mask
            
            else:
                print("✗ Invalid NDWI input for water mask")
                return None
                
        except Exception as e:
            print(f"✗ Error creating water mask: {e}")
            return None
    
    def calculate_water_area(self, water_mask, region_geometry, pixel_area_sqm=900):
        """
        Calculate water/lake area from water mask.
        
        Args:
            water_mask: Binary water mask (1 = water)
            region_geometry: GeoJSON polygon for region of interest (required for GEE)
            pixel_area_sqm: Area of each pixel in square meters
                           (900 sqm = 30m x 30m for Sentinel-2)
            
        Returns:
            dict with area statistics
        """
        
        try:
            # If EE Image
            if hasattr(water_mask, "reduceRegion"):
                if ee is None:
                    raise RuntimeError("Earth Engine not available")
                
                ee_geometry = ee.Geometry(region_geometry)
                
                pixel_counts = water_mask.reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=ee_geometry,
                    scale=30,
                    maxPixels=10_000_000,
                    bestEffort=True
                ).getInfo()
                pixel_count = next(iter(pixel_counts.values()), 0) if pixel_counts else 0
                pixel_count = pixel_count or 0
                
                area_sqm = pixel_count * pixel_area_sqm
                area_sqkm = area_sqm / 1e6
                
                self.last_lake_area = {
                    "area_sqm": area_sqm,
                    "area_sqkm": area_sqkm,
                    "pixels": pixel_count,
                    "pixel_area_sqm": pixel_area_sqm
                }
                
                print(f"✓ Water area calculated: {area_sqkm:.2f} km²")
                return self.last_lake_area
            
            # If numeric (for demo/simulation)
            elif isinstance(water_mask, (int, float)):
                # Simulate area based on water mask presence
                if water_mask > 0:
                    # Demo: simulate water area (not real)
                    simulated_area_sqkm = np.random.uniform(5, 50)  # 5-50 km² demo range
                    self.last_lake_area = {
                        "area_sqkm": simulated_area_sqkm,
                        "water_detected": True,
                        "note": "Demo simulated area"
                    }
                else:
                    self.last_lake_area = {
                        "area_sqkm": 0,
                        "water_detected": False
                    }
                
                print(f"✓ Water area: {self.last_lake_area['area_sqkm']:.2f} km²")
                return self.last_lake_area
            
            else:
                print("✗ Invalid water mask for area calculation")
                return None
                
        except Exception as e:
            print(f"✗ Error calculating water area: {e}")
            return None
    
    def analyze_water_change(self, current_area_sqkm, previous_area_sqkm):
        """
        Analyze change in water area (useful for trend detection).
        
        Args:
            current_area_sqkm: Current water area in km²
            previous_area_sqkm: Previous water area in km²
            
        Returns:
            dict with change statistics
        """
        
        if previous_area_sqkm == 0:
            percent_change = 0
        else:
            percent_change = ((current_area_sqkm - previous_area_sqkm) / previous_area_sqkm) * 100
        
        absolute_change = current_area_sqkm - previous_area_sqkm
        
        result = {
            "current_area_sqkm": current_area_sqkm,
            "previous_area_sqkm": previous_area_sqkm,
            "absolute_change_sqkm": absolute_change,
            "percent_change": percent_change,
            "trend": "increasing" if absolute_change > 0 else "decreasing" if absolute_change < 0 else "stable",
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"✓ Water change: {absolute_change:+.2f} km² ({percent_change:+.1f}%)")
        return result


class WaterObservation:
    """Encapsulates a single water observation (satellite-derived)."""
    
    def __init__(self, region, date, ndwi_value, water_area_sqkm, cloud_cover_percent):
        """
        Create water observation record.
        
        Args:
            region: Region name
            date: Observation date (datetime or string)
            ndwi_value: NDWI value
            water_area_sqkm: Water area in km²
            cloud_cover_percent: Cloud cover percentage
        """
        
        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d")
        
        self.region = region
        self.date = date
        self.ndwi_value = ndwi_value
        self.water_area_sqkm = water_area_sqkm
        self.cloud_cover_percent = cloud_cover_percent
        self.source = "satellite_observation"
    
    def to_dict(self):
        """Convert to dictionary for JSON/CSV export."""
        return {
            "region": self.region,
            "date": self.date.isoformat(),
            "ndwi_value": round(self.ndwi_value, 4),
            "water_area_sqkm": round(self.water_area_sqkm, 2),
            "cloud_cover_percent": self.cloud_cover_percent,
            "source": self.source
        }
    
    def to_json_string(self):
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
