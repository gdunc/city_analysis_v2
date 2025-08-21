from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple
import requests
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class ElevationResult:
    """Result from elevation lookup with metadata."""
    elevation: Optional[float]  # meters, None if not found
    source: str  # which service provided the data
    confidence: float  # confidence score 0.0-1.0
    cached: bool = False

class ElevationService:
    """Multi-source elevation data service with fallback logic."""
    
    def __init__(self, google_api_key: Optional[str] = None):
        self.google_api_key = google_api_key
        self.cache: Dict[Tuple[float, float], ElevationResult] = {}
        self.request_counts = {"opentopo": 0, "google": 0, "open_elevation": 0}
        
    def get_elevation(self, lat: float, lon: float, use_cache: bool = True) -> ElevationResult:
        """Get elevation for coordinates using multiple sources with fallback."""
        cache_key = (round(lat, 4), round(lon, 4))
        
        if use_cache and cache_key in self.cache:
            result = self.cache[cache_key]
            result.cached = True
            return result
        
        # Try sources in order of preference
        sources = [
            ("opentopo", self._try_opentopo),
            ("google", self._try_google),
            ("open_elevation", self._try_open_elevation),
        ]
        
        for source_name, source_func in sources:
            try:
                result = source_func(lat, lon)
                if result.elevation is not None:
                    self.cache[cache_key] = result
                    self.request_counts[source_name] += 1
                    return result
                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                logger.debug(f"Elevation source {source_name} failed: {e}")
                continue
        
        # No elevation found from any source
        result = ElevationResult(elevation=None, source="none", confidence=0.0)
        self.cache[cache_key] = result
        return result
    
    def _try_opentopo(self, lat: float, lon: float) -> ElevationResult:
        """Try OpenTopoData API (free, good coverage)."""
        url = "https://api.opentopodata.org/v1/aster30m"
        params = {"locations": f"{lat},{lon}"}
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") == "OK" and data.get("results"):
                result = data["results"][0]
                elevation = result.get("elevation")
                if elevation is not None:
                    return ElevationResult(
                        elevation=float(elevation),
                        source="opentopo",
                        confidence=0.9
                    )
        except Exception as e:
            logger.debug(f"OpenTopoData failed: {e}")
        
        return ElevationResult(elevation=None, source="opentopo", confidence=0.0)
    
    def _try_google(self, lat: float, lon: float) -> ElevationResult:
        """Try Google Elevation API (requires API key)."""
        if not self.google_api_key:
            return ElevationResult(elevation=None, source="google", confidence=0.0)
        
        url = "https://maps.googleapis.com/maps/api/elevation/json"
        params = {
            "locations": f"{lat},{lon}",
            "key": self.google_api_key
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") == "OK" and data.get("results"):
                result = data["results"][0]
                elevation = result.get("elevation")
                if elevation is not None:
                    return ElevationResult(
                        elevation=float(elevation),
                        source="google",
                        confidence=0.95
                    )
        except Exception as e:
            logger.debug(f"Google Elevation API failed: {e}")
        
        return ElevationResult(elevation=None, source="google", confidence=0.0)
    
    def _try_open_elevation(self, lat: float, lon: float) -> ElevationResult:
        """Try Open-Elevation API (free, self-hosted option)."""
        # Try multiple Open-Elevation endpoints
        endpoints = [
            "https://api.open-elevation.com/api/v1/lookup",
            "https://elevation-api.io/api/v1/lookup",
        ]
        
        for endpoint in endpoints:
            try:
                params = {"locations": f"{lat},{lon}"}
                resp = requests.get(endpoint, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                
                if data.get("results"):
                    result = data["results"][0]
                    elevation = result.get("elevation")
                    if elevation is not None:
                        return ElevationResult(
                            elevation=float(elevation),
                            source="open_elevation",
                            confidence=0.85
                        )
            except Exception as e:
                logger.debug(f"Open-Elevation {endpoint} failed: {e}")
                continue
        
        return ElevationResult(elevation=None, source="open_elevation", confidence=0.0)
    
    def get_elevation_batch(self, coordinates: List[Tuple[float, float]], 
                           batch_size: int = 100) -> List[ElevationResult]:
        """Get elevation for multiple coordinates with batching."""
        results = []
        
        for i in range(0, len(coordinates), batch_size):
            batch = coordinates[i:i + batch_size]
            batch_results = []
            
            for lat, lon in batch:
                result = self.get_elevation(lat, lon)
                batch_results.append(result)
                time.sleep(0.1)  # Rate limiting between requests
            
            results.extend(batch_results)
            
            # Progress logging
            if len(coordinates) > batch_size:
                logger.info(f"Processed elevation batch {i//batch_size + 1}/{(len(coordinates) + batch_size - 1)//batch_size}")
        
        return results
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about elevation data sources used."""
        return {
            "total_requests": sum(self.request_counts.values()),
            "cache_hits": len([r for r in self.cache.values() if r.cached]),
            "cache_size": len(self.cache),
            **self.request_counts
        }

def enrich_places_with_elevation(places: List[Dict], 
                                google_api_key: Optional[str] = None,
                                batch_size: int = 100) -> List[Dict]:
    """Enrich place records with elevation data from multiple sources."""
    if not places:
        return places
    
    service = ElevationService(google_api_key=google_api_key)
    
    # Extract coordinates for batch processing
    coordinates = [(float(p["latitude"]), float(p["longitude"])) for p in places]
    
    logger.info(f"Fetching elevation data for {len(places)} places...")
    elevation_results = service.get_elevation_batch(coordinates, batch_size=batch_size)
    
    # Merge elevation data back into place records
    enriched_places = []
    for place, elevation_result in zip(places, elevation_results):
        enriched_place = place.copy()
        
        # Only add elevation if we don't already have it
        if place.get("elevation") is None and elevation_result.elevation is not None:
            enriched_place["elevation"] = elevation_result.elevation
            enriched_place["elevation_source"] = elevation_result.source
            enriched_place["elevation_confidence"] = elevation_result.confidence
        
        # Add elevation in feet if we have elevation data (from any source)
        if enriched_place.get("elevation") is not None:
            # Convert meters to feet (1 meter = 3.28084 feet)
            elevation_meters = enriched_place["elevation"]
            elevation_feet = round(elevation_meters * 3.28084, 1)
            enriched_place["elevation_feet"] = elevation_feet
        
        enriched_places.append(enriched_place)
    
    # Log statistics
    stats = service.get_stats()
    logger.info(f"Elevation enrichment complete. Stats: {stats}")
    
    return enriched_places
