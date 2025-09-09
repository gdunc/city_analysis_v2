from __future__ import annotations

import math
from typing import Dict, Iterable, List

from shapely.geometry import Point, Polygon, MultiPolygon


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def filter_within_perimeter(
    places: Iterable[Dict],
    perimeter: Polygon | MultiPolygon,
) -> List[Dict]:
    results: List[Dict] = []
    for p in places:
        lat = float(p["latitude"])  # type: ignore[index]
        lon = float(p["longitude"])  # type: ignore[index]
        if perimeter.contains(Point(lon, lat)):
            results.append(p)
    return results


def enforce_min_population(places: Iterable[Dict], min_population: int) -> List[Dict]:
    return [p for p in places if int(p.get("population") or 0) >= min_population]


def dedupe_places(
    places: Iterable[Dict],
    distance_km_threshold: float = 10.0,
) -> List[Dict]:
    """Dedupe by normalized name+country, preferring larger population and merging close coords.

    If country is empty, treat name-only as a key which may keep distinct far-apart places.
    """
    # Sort by population descending to keep the largest first
    sorted_places = sorted(places, key=lambda r: (int(r.get("population") or 0)), reverse=True)

    seen: List[Dict] = []
    for p in sorted_places:
        name_key = _normalize_name(str(p.get("name", "")))
        country_key = str(p.get("country", "")).upper()
        lat = float(p["latitude"])  # type: ignore[index]
        lon = float(p["longitude"])  # type: ignore[index]

        duplicate_found = False
        for kept in seen:
            same_name = _normalize_name(str(kept.get("name", ""))) == name_key
            same_country = str(kept.get("country", "")).upper() == country_key or not country_key or not kept.get("country")
            if same_name and same_country:
                d = _haversine_km(lat, lon, float(kept["latitude"]), float(kept["longitude"]))
                if d <= distance_km_threshold:
                    duplicate_found = True
                    break
        if not duplicate_found:
            seen.append(p)
    return seen
