"""
satellite/image_cache.py

Local cache for GEE image exports to avoid URL access issues.
Ensures YOLOv8 can access images without network/authentication problems.
"""

import os
import hashlib
import requests
from datetime import datetime, timedelta
from pathlib import Path
import json

class GEEImageCache:
    """Local cache for GEE image exports to avoid URL access issues."""
    
    def __init__(self, cache_dir="./gee_cache", max_age_hours=24, max_size_mb=500):
        """
        Initialize image cache.
        
        Args:
            cache_dir: Directory for cached images
            max_age_hours: Maximum age of cached items before refresh
            max_size_mb: Maximum cache size in MB
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.max_age = timedelta(hours=max_age_hours)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        self.metadata = self._load_metadata()
        
    def _load_metadata(self):
        """Load cache metadata from disk."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_metadata(self):
        """Save cache metadata to disk."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
    
    def _generate_cache_key(self, region_key, image_id, band_config="rgb"):
        """Generate unique cache key for image request."""
        key_string = f"{region_key}_{image_id}_{band_config}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _get_cache_path(self, cache_key, extension=".png"):
        """Get file path for cached image."""
        return self.cache_dir / f"{cache_key}{extension}"
    
    def download_and_cache_image(self, image_url, region_key, image_id, 
                                band_config="rgb", dimensions=512):
        """
        Download image from GEE URL and cache locally.
        
        Args:
            image_url: GEE thumbnail URL
            region_key: Region identifier
            image_id: Sentinel-2 image ID
            band_config: Band configuration (rgb, ndwi, etc.)
            dimensions: Image dimensions in pixels
            
        Returns:
            tuple: (local_path, success, metadata)
        """
        cache_key = self._generate_cache_key(region_key, image_id, band_config)
        cache_path = self._get_cache_path(cache_key)
        
        # Check if already cached and valid
        if cache_path.exists():
            try:
                cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
                if cache_age < self.max_age:
                    print(f"✓ Using cached image: {cache_path.name}")
                    return str(cache_path), True, {
                        "source": "cache",
                        "cache_age_hours": cache_age.total_seconds() / 3600,
                        "cache_hit": True
                    }
                else:
                    print(f"✗ Cache expired: {cache_path.name}")
                    cache_path.unlink()
            except Exception as e:
                print(f"✗ Cache check failed: {e}")
        
        # Download and cache
        try:
            print(f"→ Downloading image from GEE URL...")
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            # Save to cache
            with open(cache_path, 'wb') as f:
                f.write(response.content)
            
            # Update metadata
            self.metadata[cache_key] = {
                "region_key": region_key,
                "image_id": image_id,
                "band_config": band_config,
                "cached_at": datetime.now().isoformat(),
                "file_size_bytes": cache_path.stat().st_size,
                "original_url": image_url
            }
            self._save_metadata()
            
            print(f"✓ Image cached: {cache_path.name}")
            return str(cache_path), True, {
                "source": "downloaded",
                "cache_hit": False,
                "file_size_bytes": cache_path.stat().st_size
            }
            
        except Exception as e:
            print(f"✗ Failed to download image: {e}")
            return None, False, {
                "source": "error",
                "error": str(e),
                "cache_hit": False
            }
    
    def get_cached_image_path(self, region_key, image_id, band_config="rgb"):
        """
        Get cached image path if available and valid.
        
        Args:
            region_key: Region identifier
            image_id: Sentinel-2 image ID
            band_config: Band configuration
            
        Returns:
            str: Local path if cached and valid, None otherwise
        """
        cache_key = self._generate_cache_key(region_key, image_id, band_config)
        cache_path = self._get_cache_path(cache_key)
        
        if cache_path.exists():
            try:
                cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
                if cache_age < self.max_age:
                    return str(cache_path)
            except:
                pass
        
        return None
    
    def clear_cache(self):
        """Clear all cached images."""
        for file in self.cache_dir.glob("*"):
            if file.is_file() and file != self.metadata_file:
                file.unlink()
        self.metadata = {}
        self._save_metadata()
        print("✓ Cache cleared")
    
    def get_cache_stats(self):
        """Get cache statistics."""
        total_size = sum(f.stat().st_size for f in self.cache_dir.glob("*") if f.is_file())
        file_count = len(list(self.cache_dir.glob("*")))
        
        return {
            "cache_dir": str(self.cache_dir),
            "file_count": file_count,
            "total_size_mb": total_size / (1024 * 1024),
            "max_size_mb": self.max_size_bytes / (1024 * 1024),
            "max_age_hours": self.max_age.total_seconds() / 3600
        }


# Global cache instance
_global_cache = None

def get_image_cache():
    """Get global image cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = GEEImageCache()
    return _global_cache