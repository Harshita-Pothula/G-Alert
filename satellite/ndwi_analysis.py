"""
satellite/ndwi_analysis.py

Normalized Difference Water Index (NDWI) calculation for water/lake detection.
NDWI = (Green - NIR) / (Green + NIR)

For Sentinel-2:
- Green = B3
- NIR = B8

Note: NDWI threshold of 0.3 is a general water detection threshold from McFeeters (1996).
For glacial lake monitoring, this threshold may not be optimal due to:
- Snow/ice interference in high-altitude environments
- Turbid water from glacial melt
- Shadow effects in mountainous terrain

This implementation uses the general threshold but acknowledges its limitations
for Himalayan glacial lake applications. Future refinement should use region-specific
calibration based on in-situ validation data.

Pixel-level quality masking (this module):
The live pipeline additionally masks obvious non-water contamination using the
Sentinel-2 Scene Classification Layer (SCL band in COPERNICUS/S2_SR_HARMONIZED):
cloud shadow (3), medium/high-probability cloud (8/9), thin cirrus (10), and
snow/ice (11) are excluded before NDWI and water-area computation. SCL masking
removes gross contamination; it does NOT validate the NDWI threshold, and
terrain-shadow / turbid-water limitations remain.
"""

import numpy as np
import os
from datetime import datetime
import json

# Import Earth Engine
try:
    import ee
except ImportError:
    print("ERROR: earthengine-api not installed. Run: pip install earthengine-api")
    ee = None

# Sentinel-2 Scene Classification Layer (SCL) values in
# COPERNICUS/S2_SR_HARMONIZED that are treated as contamination for water
# detection. Values follow the Sentinel-2 Level-2A / Sen2Cor scene-class
# specification (band "SCL", produced at 20 m).
SCL_CONTAMINATION_CLASSES = {
    3: "cloud_shadow",
    8: "cloud_medium_probability",
    9: "cloud_high_probability",
    10: "thin_cirrus",
    11: "snow_ice",
}

class NDWIAnalyzer:
    """Calculates NDWI and performs water detection."""
    
    def __init__(self, ndwi_water_threshold=None):
        """
        Initialize NDWI analyzer.
        
        Args:
            ndwi_water_threshold: NDWI threshold for water detection
                                 (values > threshold = water)
                                 Default 0.3 is general water detection threshold
                                 from McFeeters (1996), not calibrated for
                                 Himalayan glacial lakes
        
        Note: The default threshold is not scientifically validated for
        high-altitude glacial lake environments. Future calibration should
        use region-specific in-situ measurements.
        """
        configured_threshold = os.getenv("NDWI_WATER_THRESHOLD")
        if ndwi_water_threshold is None and configured_threshold is not None:
            try:
                ndwi_water_threshold = float(configured_threshold)
            except ValueError:
                ndwi_water_threshold = 0.3
        self.ndwi_water_threshold = ndwi_water_threshold if ndwi_water_threshold is not None else 0.3
        self.last_ndwi = None
        self.last_water_mask = None
        self.last_lake_area = None
    
    def apply_quality_mask(self, image, region_geometry=None):
        """
        Apply pixel-level quality masking to a Sentinel-2 SR image using the
        Scene Classification Layer (band "SCL").

        Excludes pixels classified as cloud shadow (3), medium-probability
        cloud (8), high-probability cloud (9), thin cirrus (10), and snow/ice
        (11). Because Earth Engine propagates masks, masked pixels are
        automatically excluded from subsequent NDWI statistics and from the
        water mask / water-area computation.

        Args:
            image: ee.Image from COPERNICUS/S2_SR_HARMONIZED (must contain the
                   "SCL" band)
            region_geometry: optional GeoJSON polygon. When provided,
                per-class contamination fractions and the valid-pixel fraction
                are computed from the ACTUAL image via reduceRegion and
                returned for transparency (no values are invented).

        Returns:
            tuple: (masked_image, masking_info dict)

            masking_info["status"]:
              "APPLIED"  - SCL masking applied (fractions included when a
                           region_geometry was given)
              "SKIPPED"  - input was not an EE image or EE is unavailable;
                           image returned UNMASKED
              "ERROR"    - masking was attempted but failed (e.g. SCL band
                           missing); image returned UNMASKED, reason reported
        """

        masking_info = {
            "status": "SKIPPED",
            "method": "Sentinel-2 SCL (Scene Classification Layer, band 'SCL')",
            "excluded_classes": {
                str(code): name for code, name in SCL_CONTAMINATION_CLASSES.items()
            },
            "note": (
                "SCL classes come from the Sen2Cor classification in the "
                "Sentinel-2 Level-2A product. Masking removes gross cloud, "
                "cloud-shadow, cirrus, and snow/ice contamination; it does not "
                "guarantee that all remaining NDWI-positive pixels are water "
                "(terrain shadow and turbid water remain known limitations)."
            ),
        }

        if ee is None or not hasattr(image, "select"):
            masking_info["reason"] = (
                "Non-Earth-Engine image input or EE unavailable; no pixel-level masking applied"
            )
            return image, masking_info

        try:
            scl = image.select("SCL")

            contamination = None
            for scl_value in SCL_CONTAMINATION_CLASSES:
                class_flag = scl.eq(int(scl_value))
                contamination = (
                    class_flag if contamination is None else contamination.Or(class_flag)
                )
            valid = contamination.Not()
            masked_image = image.updateMask(valid)
            masking_info["status"] = "APPLIED"

            if region_geometry is not None:
                # Per-class fractions and valid fraction, measured from the
                # actual image inside the analysis region (single getInfo call).
                indicator_bands = [
                    scl.eq(int(code)).float().rename(name)
                    for code, name in SCL_CONTAMINATION_CLASSES.items()
                ]
                indicator_bands.append(valid.float().rename("valid_pixel_fraction"))
                indicators = ee.Image.cat(indicator_bands)
                fractions = indicators.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=ee.Geometry(region_geometry),
                    scale=20,  # SCL is a 20 m product
                    maxPixels=10_000_000,
                    bestEffort=True,
                ).getInfo()

                valid_fraction = fractions.get("valid_pixel_fraction")
                masking_info["valid_pixel_fraction"] = (
                    round(valid_fraction, 4) if isinstance(valid_fraction, (int, float)) else None
                )
                masking_info["masked_pixel_fractions"] = {
                    key: (round(value, 4) if isinstance(value, (int, float)) else None)
                    for key, value in fractions.items()
                    if key != "valid_pixel_fraction"
                }

            return masked_image, masking_info

        except Exception as e:
            masking_info["status"] = "ERROR"
            masking_info["reason"] = f"SCL quality masking failed: {e}"
            masking_info["fallback"] = "Image used UNMASKED; results may include cloud/snow contamination"
            return image, masking_info

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
    
    def calculate_water_area(self, water_mask, region_geometry, pixel_area_sqm=900,
                             valid_pixel_mask=None, scale=30):
        """
        Calculate water/lake area from water mask.

        In the Earth Engine path, per-pixel area is derived from the actual
        image projection using ee.Image.pixelArea() at the reduceRegion scale
        (30 m) — it is NOT a fixed, assumed measurement. The pixel_area_sqm
        argument applies only to the non-EE demo/numeric branch.

        Args:
            water_mask: Binary water mask (1 = water)
            region_geometry: GeoJSON polygon for region of interest (required for GEE)
            pixel_area_sqm: Area of each pixel in square meters
                           (900 sqm = 30m x 30m for Sentinel-2; numeric branch only)
            valid_pixel_mask: Optional EE mask identifying pixels that remain
                              valid after quality masking. When provided, it
                              distinguishes an empty water result from an
                              analysis region with no valid pixels.
            
        Returns:
            dict with area statistics
        """
        
        try:
            # If EE Image
            if hasattr(water_mask, "reduceRegion"):
                if ee is None:
                    raise RuntimeError("Earth Engine not available")
                
                ee_geometry = ee.Geometry(region_geometry)
                
                valid_pixel_count = None
                if valid_pixel_mask is not None:
                    valid_count_result = valid_pixel_mask.reduceRegion(
                        reducer=ee.Reducer.sum(),
                        geometry=ee_geometry,
                        scale=scale,
                        maxPixels=10_000_000,
                        bestEffort=True
                    ).getInfo()
                    valid_pixel_count = (
                        next(iter(valid_count_result.values()), None)
                        if valid_count_result else None
                    )
                    if not isinstance(valid_pixel_count, (int, float)) or valid_pixel_count <= 0:
                        self.last_lake_area = {
                            "status": "NO_VALID_PIXELS",
                            "area_sqm": None,
                            "area_sqkm": None,
                            "pixel_area_source": "ee.Image.pixelArea() (projection-derived)"
                        }
                        return self.last_lake_area

                pixel_area_image = ee.Image.pixelArea().updateMask(water_mask)

                area_result = pixel_area_image.reduceRegion(
                   reducer=ee.Reducer.sum(),
                   geometry=ee_geometry,
                   scale=scale,
                   maxPixels=10_000_000,
                   bestEffort=True
                ).getInfo()

                if area_result:
                    area_sqm = next(iter(area_result.values()), None)
                    area_sqm = area_sqm if area_sqm is not None else 0
                elif valid_pixel_count is not None:
                    # Valid pixels exist, so an empty water mask is a real
                    # zero-water observation rather than missing data.
                    area_sqm = 0
                else:
                    self.last_lake_area = {
                        "status": "NO_VALID_PIXELS",
                        "area_sqm": None,
                        "area_sqkm": None,
                        "pixel_area_source": "ee.Image.pixelArea() (projection-derived)"
                    }
                    return self.last_lake_area
                
                area_sqkm = area_sqm / 1e6

                self.last_lake_area = {
                 "status": "SUCCESS",
                 "area_sqm": area_sqm,
                 "area_sqkm": area_sqkm,
                 "water_detected": area_sqm > 0,
                 "pixel_area_source": "ee.Image.pixelArea() (projection-derived)"
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
