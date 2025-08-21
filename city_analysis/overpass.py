from __future__ import annotations

import time
from typing import Dict, List, Sequence, Tuple

import requests

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]

DEFAULT_HEADERS = {
    "User-Agent": "city-analysis-alps/0.1 (contact: your-email@example.com)",
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
                return _try_overpass(endpoint, query)
            except Exception as e:
                last_error = e
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

    lat = south
    while lat < north:
        next_lat = min(north, lat + tile_size_deg)
        lon = west
        while lon < east:
            next_lon = min(east, lon + tile_size_deg)
            tile_bbox = (lat, lon, next_lat, next_lon)
            q = build_overpass_query(tile_bbox, place_types=place_types, require_population_tag=require_population_tag)
            try:
                chunk = fetch_overpass_places(q)
                for r in chunk:
                    key = (r.get("name"), round(float(r["latitude"]), 4), round(float(r["longitude"]), 4))
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    results.append(r)
            except Exception:
                # Skip failing tile and continue; Overpass may be flaky
                pass
            time.sleep(sleep_between)
            lon = next_lon
        lat = next_lat
    return results
