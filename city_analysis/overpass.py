from __future__ import annotations

import time
from typing import Dict, List, Sequence, Tuple
import logging

import requests

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]

DEFAULT_HEADERS = {
    "User-Agent": "city-analysis/0.1 (+contact: your-email@example.com)",
}


def build_overpass_query(
    bbox: Tuple[float, float, float, float],
    place_types: Sequence[str] = ("city", "town", "village"),
    require_population_tag: bool = False,
) -> str:
    """Build an Overpass QL query for places within a bounding box.

    Args:
        bbox: (south, west, north, east)
        place_types: OSM place values to include.
        require_population_tag: If True, only return features with a population tag.
    """
    place_regex = "|".join(place_types)
    pop_filter = "[\"population\"]" if require_population_tag else ""
    bbox_str = ",".join(str(x) for x in bbox)
    query = f"""
    [out:json][timeout:90];
    (
      node["place"~"^({place_regex})$"]{pop_filter}({bbox_str});
      way["place"~"^({place_regex})$"]{pop_filter}({bbox_str});
      relation["place"~"^({place_regex})$"]{pop_filter}({bbox_str});
    );
    out center;
    """
    return query


def _try_overpass(endpoint: str, query: str) -> List[Dict]:
    logging.info(f"Overpass: POST {endpoint}")
    resp = requests.post(endpoint, data={"data": query}, headers=DEFAULT_HEADERS, timeout=120)
    resp.raise_for_status()
    # Ensure proper UTF-8 encoding
    resp.encoding = 'utf-8'
    payload = resp.json()
    # Overpass may return remarks/errors; still parse elements if present
    elements = payload.get("elements", [])
    results: List[Dict] = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        population = None
        if "population" in tags:
            try:
                population = int(str(tags.get("population")).replace(" ", ""))
            except Exception:
                population = None
        
        # Extract elevation if available
        elevation = None
        if "ele" in tags:
            try:
                elevation = float(str(tags.get("ele")).replace(" ", ""))
            except (ValueError, TypeError):
                elevation = None
        elif "height" in tags:
            try:
                elevation = float(str(tags.get("height")).replace(" ", ""))
            except (ValueError, TypeError):
                elevation = None
        
        lat, lon = None, None
        if el.get("type") == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")
        if lat is None or lon is None:
            continue
        country = tags.get("addr:country") or tags.get("is_in:country_code") or tags.get("ISO3166-1")
        results.append(
            {
                "name": name,
                "country": (country or ""),
                "latitude": float(lat),
                "longitude": float(lon),
                "population": population if population is not None else 0,
                "elevation": elevation,
                "source": "osm",
            }
        )
    return results


def fetch_overpass_places(query: str, max_retries_per_endpoint: int = 2) -> List[Dict]:
    """Execute an Overpass query with endpoint fallback and simple backoff.

    Returns list of dicts with keys: name, country (if available), latitude, longitude, population, source
    """
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(max_retries_per_endpoint):
            try:
                results = _try_overpass(endpoint, query)
                logging.info(f"Overpass: success on {endpoint} (attempt {attempt+1}) elements={len(results)}")
                return results
            except Exception as e:
                last_error = e
                logging.warning(f"Overpass: error on {endpoint} (attempt {attempt+1}): {e}")
                # Exponential backoff with jitter
                time.sleep(1.5 * (attempt + 1))
        # try next endpoint
    if last_error:
        raise last_error
    return []


def fetch_overpass_bbox_tiled(
    bbox: Tuple[float, float, float, float],
    place_types: Sequence[str] = ("city", "town"),
    require_population_tag: bool = False,
    tile_size_deg: float = 1.0,
    sleep_between: float = 0.5,
) -> List[Dict]:
    """Split a bbox into tiles and aggregate Overpass results to avoid huge queries.

    Dedupe across tiles by (name, rounded lat/lon).
    """
    south, west, north, east = bbox
    results: List[Dict] = []
    seen_keys = set()

    # Compute number of tiles for progress
    total_tiles_lat = max(1, int((north - south + 1e-9) // tile_size_deg + (1 if (south + ((int((north - south) / tile_size_deg)) * tile_size_deg)) < north else 0)))
    total_tiles_lon = max(1, int((east - west + 1e-9) // tile_size_deg + (1 if (west + ((int((east - west) / tile_size_deg)) * tile_size_deg)) < east else 0)))
    approx_total_tiles = total_tiles_lat * total_tiles_lon
    logging.info(f"Overpass tiling: bbox={bbox} tile_size={tile_size_deg} approx_tiles={approx_total_tiles}")

    lat = south
    tile_index = 0
    while lat < north:
        next_lat = min(north, lat + tile_size_deg)
        lon = west
        while lon < east:
            next_lon = min(east, lon + tile_size_deg)
            tile_bbox = (lat, lon, next_lat, next_lon)
            tile_index += 1
            logging.info(f"Overpass tile {tile_index}/{approx_total_tiles}: {tile_bbox}")
            q = build_overpass_query(tile_bbox, place_types=place_types, require_population_tag=require_population_tag)
            try:
                chunk = fetch_overpass_places(q)
                logging.info(f"Overpass tile {tile_index}: received {len(chunk)} elements")
                for r in chunk:
                    key = (r.get("name"), round(float(r["latitude"]), 4), round(float(r["longitude"]), 4))
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    results.append(r)
            except Exception as e:
                logging.warning(f"Overpass tile {tile_index}: failed with {e}; continuing")
            time.sleep(sleep_between)
            lon = next_lon
        lat = next_lat
    logging.info(f"Overpass complete: total unique places {len(results)}")
    return results


# --- Hospital POIs (amenity/healthcare=hospital) ---

def build_overpass_hospitals_query(
    bbox: Tuple[float, float, float, float],
) -> str:
    """Build an Overpass QL query for hospitals within a bounding box.

    Args:
        bbox: (south, west, north, east)
    """
    bbox_str = ",".join(str(x) for x in bbox)
    # Include both legacy and modern tagging styles
    query = f"""
    [out:json][timeout:120];
    (
      node["amenity"="hospital"]({bbox_str});
      way["amenity"="hospital"]({bbox_str});
      relation["amenity"="hospital"]({bbox_str});
      node["healthcare"="hospital"]({bbox_str});
      way["healthcare"="hospital"]({bbox_str});
      relation["healthcare"="hospital"]({bbox_str});
    );
    out center;
    """
    return query


def _try_overpass_hospitals(endpoint: str, query: str) -> List[Dict]:
    resp = requests.post(endpoint, data={"data": query}, headers=DEFAULT_HEADERS, timeout=180)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    payload = resp.json()
    elements = payload.get("elements", [])
    results: List[Dict] = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or ""
        # Get center point for ways/relations, lat/lon for nodes
        lat, lon = None, None
        if el.get("type") == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")
        if lat is None or lon is None:
            continue
        results.append(
            {
                "name": name,
                "latitude": float(lat),
                "longitude": float(lon),
                "source": "osm",
                "_tags": tags,
            }
        )
    return results


def fetch_overpass_hospitals(query: str, max_retries_per_endpoint: int = 2) -> List[Dict]:
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(max_retries_per_endpoint):
            try:
                return _try_overpass_hospitals(endpoint, query)
            except Exception as e:
                last_error = e
                time.sleep(1.5 * (attempt + 1))
    if last_error:
        raise last_error
    return []


def fetch_overpass_hospitals_bbox_tiled(
    bbox: Tuple[float, float, float, float],
    tile_size_deg: float = 1.0,
    sleep_between: float = 0.5,
) -> List[Dict]:
    """Split a bbox into tiles and aggregate Overpass results for hospitals.

    Dedupe across tiles by rounded lat/lon/name.
    """
    south, west, north, east = bbox
    results: List[Dict] = []
    seen_keys = set()

    lat = south
    while lat < north:
        next_lat = min(north, lat + tile_size_deg)
        lon = west
        while lon < east:
            next_lon = min(east, lon + tile_size_deg)
            tile_bbox = (lat, lon, next_lat, next_lon)
            q = build_overpass_hospitals_query(tile_bbox)
            try:
                chunk = fetch_overpass_hospitals(q)
                for r in chunk:
                    key = (
                        r.get("name") or "",
                        round(float(r["latitude"]), 4),
                        round(float(r["longitude"]), 4),
                    )
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    results.append(r)
            except Exception:
                # Skip failing tile and continue
                pass
            time.sleep(sleep_between)
            lon = next_lon
        lat = next_lat
    return results
