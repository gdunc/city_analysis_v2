import logging
from typing import Dict, Iterable, List, Optional, Tuple, Union
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.ops import nearest_points
from shapely.validation import make_valid
from shapely.errors import TopologicalError

logger = logging.getLogger(__name__)

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great circle distance between two points using Haversine formula."""
    import math
    
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Earth's radius in kilometers
    r = 6371.0
    return r * c

def _vincenty_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance using Vincenty formula (more accurate than Haversine)."""
    import math
    
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # WGS84 ellipsoid parameters
    a = 6378.137  # semi-major axis in km
    f = 1/298.257223563  # flattening
    b = a * (1 - f)  # semi-minor axis
    
    L = lon2 - lon1
    U1 = math.atan((1 - f) * math.tan(lat1))
    U2 = math.atan((1 - f) * math.tan(lat2))
    
    sinU1 = math.sin(U1)
    cosU1 = math.cos(U1)
    sinU2 = math.sin(U2)
    cosU2 = math.cos(U2)
    
    lambda_ = L
    iterLimit = 100
    
    while iterLimit > 0:
        sinLambda = math.sin(lambda_)
        cosLambda = math.cos(lambda_)
        sinSigma = math.sqrt((cosU2 * sinLambda) ** 2 + (cosU1 * sinU2 - sinU1 * cosU2 * cosLambda) ** 2)
        
        if sinSigma == 0:
            return 0.0
        
        cosSigma = sinU1 * sinU2 + cosU1 * cosU2 * cosLambda
        sigma = math.atan2(sinSigma, cosSigma)
        sinAlpha = cosU1 * cosU2 * sinLambda / sinSigma
        cosSqAlpha = 1 - sinAlpha ** 2
        
        try:
            cos2SigmaM = cosSigma - 2 * sinU1 * sinU2 / cosSqAlpha
        except ZeroDivisionError:
            cos2SigmaM = 0
        
        C = f / 16 * cosSqAlpha * (4 + f * (4 - 3 * cosSqAlpha))
        lambdaP = lambda_
        lambda_ = L + (1 - C) * f * sinAlpha * (sigma + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1 + 2 * cos2SigmaM ** 2)))
        
        if abs(lambda_ - lambdaP) <= 1e-12:
            break
        iterLimit -= 1
    
    if iterLimit == 0:
        # Fallback to Haversine if Vincenty fails
        return _haversine_km(math.degrees(lat1), math.degrees(lon1), math.degrees(lat2), math.degrees(lon2))
    
    uSq = cosSqAlpha * (a ** 2 - b ** 2) / b ** 2
    A = 1 + uSq / 16384 * (4096 + uSq * (-768 + uSq * (320 - 175 * uSq)))
    B = uSq / 1024 * (256 + uSq * (-128 + uSq * (74 - 47 * uSq)))
    deltaSigma = B * sinSigma * (cos2SigmaM + B / 4 * (cosSigma * (-1 + 2 * cos2SigmaM ** 2) - B / 6 * cos2SigmaM * (-3 + 4 * sinSigma ** 2) * (-3 + 4 * cos2SigmaM ** 2)))
    
    s = b * A * (sigma - deltaSigma)
    return s

def _validate_and_fix_polygon(perimeter: Union[Polygon, MultiPolygon]) -> Optional[Union[Polygon, MultiPolygon]]:
    """Validate and fix polygon geometry if needed."""
    try:
        if perimeter.is_valid:
            return perimeter
        
        # Try to fix invalid geometry
        fixed = make_valid(perimeter)
        if fixed.is_valid:
            logger.info("Fixed invalid polygon geometry")
            return fixed
        else:
            logger.warning("Could not fix invalid polygon geometry, trying simplification")
            try:
                simplified = fixed.simplify(0.001)  # Simplify with 1km tolerance
                if simplified.is_valid:
                    logger.info("Simplified polygon geometry successfully")
                    return simplified
            except Exception:
                pass
            
            logger.warning("Could not fix or simplify polygon geometry")
            return None
    except Exception as e:
        logger.error(f"Error validating polygon: {e}")
        return None

def _calculate_distance_to_polygon(pt: Point, perimeter: Union[Polygon, MultiPolygon]) -> Optional[float]:
    """Calculate distance from point to polygon boundary."""
    try:
        if perimeter.contains(pt):
            return 0.0
        
        # Find nearest point on boundary
        nearest = nearest_points(perimeter.boundary, pt)[0]
        
        # Try Vincenty first (more accurate)
        try:
            dist_km = _vincenty_km(
                pt.y, pt.x,  # lat, lon
                nearest.y, nearest.x  # lat, lon
            )
            return dist_km
        except Exception:
            # Fallback to Haversine
            dist_km = _haversine_km(
                pt.y, pt.x,  # lat, lon
                nearest.y, nearest.x  # lat, lon
            )
            return dist_km
            
    except TopologicalError as e:
        logger.debug(f"Topological error in boundary distance calculation: {e}")
        return None
    except Exception as e:
        logger.debug(f"Boundary distance calculation failed: {e}")
        return None

def _calculate_centroid_distance(pt: Point, perimeter: Union[Polygon, MultiPolygon]) -> float:
    """Calculate distance from point to polygon centroid as fallback."""
    try:
        centroid = perimeter.centroid
        dist_km = _vincenty_km(
            pt.y, pt.x,  # lat, lon
            centroid.y, centroid.x  # lat, lon
        )
        return dist_km
    except Exception:
        # Fallback to Haversine
        try:
            dist_km = _haversine_km(
                pt.y, pt.x,  # lat, lon
                centroid.y, centroid.x  # lat, lon
            )
            return dist_km
        except Exception as e:
            logger.error(f"All distance calculation methods failed: {e}")
            return float('inf')

def _calculate_bounding_box_distance(pt: Point, perimeter: Union[Polygon, MultiPolygon]) -> float:
    """Calculate distance to bounding box as last resort fallback."""
    try:
        bounds = perimeter.bounds  # (minx, miny, maxx, maxy)
        min_lon, min_lat, max_lon, max_lat = bounds
        
        # Find closest point on bounding box
        closest_lon = max(min_lon, min(pt.x, max_lon))
        closest_lat = max(min_lat, min(pt.y, max_lat))
        
        dist_km = _haversine_km(
            pt.y, pt.x,  # lat, lon
            closest_lat, closest_lon  # lat, lon
        )
        return dist_km
    except Exception as e:
        logger.error(f"Bounding box distance calculation failed: {e}")
        return float('inf')

def add_distance_to_perimeter_km(
    records: Iterable[Dict],
    perimeter: Union[Polygon, MultiPolygon],
    *,
    region_slug: str = "alps",
) -> List[Dict]:
    """Add distance to region perimeter for each place record with robust fallback methods.

    Writes the distance into a region-agnostic field name: distance_km_to_perimeter.
    For backward compatibility, also fills distance_km_to_<slug> (e.g., _to_alps).
    """
    
    # Validate and fix polygon if needed
    valid_perimeter = _validate_and_fix_polygon(perimeter)
    if not valid_perimeter:
        logger.error("Invalid perimeter geometry, cannot calculate distances")
        return [
            {**r, "distance_km_to_perimeter": None, f"distance_km_to_{region_slug}": None}
            for r in records
        ]
    
    logger.info(f"Calculating distances using perimeter with bounds: {valid_perimeter.bounds}")
    
    updated: List[Dict] = []
    success_count = 0
    error_count = 0
    fallback_count = 0
    
    for r in records:
        try:
            lat = float(r["latitude"])
            lon = float(r["longitude"])
            pt = Point(lon, lat)
            
            # Method 1: Try boundary distance first (most accurate)
            dist_km = _calculate_distance_to_polygon(pt, valid_perimeter)
            
            # Method 2: Fallback to centroid distance
            if dist_km is None:
                dist_km = _calculate_centroid_distance(pt, valid_perimeter)
                fallback_count += 1
                logger.debug(f"Used centroid fallback for {r.get('name', 'unknown')}")
            
            # Method 3: Last resort - bounding box distance
            if dist_km is None or dist_km == float('inf'):
                dist_km = _calculate_bounding_box_distance(pt, valid_perimeter)
                fallback_count += 1
                logger.debug(f"Used bounding box fallback for {r.get('name', 'unknown')}")
            
            # Final validation
            if dist_km is None or dist_km == float('inf'):
                error_count += 1
                logger.warning(f"All distance methods failed for {r.get('name', 'unknown')}")
                r = {**r, "distance_km_to_perimeter": None, f"distance_km_to_{region_slug}": None}
            else:
                # Round to 3 decimal places
                dist_km = round(dist_km, 3)
                success_count += 1
                r = {**r, "distance_km_to_perimeter": dist_km, f"distance_km_to_{region_slug}": dist_km}
            
        except Exception as e:
            error_count += 1
            logger.warning(f"Failed to calculate distance for {r.get('name', 'unknown')}: {e}")
            r = {**r, "distance_km_to_perimeter": None, f"distance_km_to_{region_slug}": None}
        
        updated.append(r)
    
    logger.info(f"Distance calculation complete: {success_count} successful, {fallback_count} fallbacks, {error_count} errors")
    return updated
