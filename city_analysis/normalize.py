from __future__ import annotations

import math
from typing import Dict, Iterable, List

from shapely.geometry import Point, Polygon, MultiPolygon
from .country_filters import infer_country_by_bbox
from .country_lookup import infer_country_iso_a2


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
    allowed_countries: Iterable[str] | None = None,
) -> List[Dict]:
    """Dedupe by normalized name and proximity; resolve cross-country conflicts.

    Rules:
    - Group by normalized name; consider duplicates when within distance_km_threshold.
    - Prefer GeoNames over OSM when both represent the same place.
    - If sources disagree on country, prefer bbox-inferred country; if still tied, keep
      the country from the preferred source (GeoNames), else fall back to the record
      with larger population.
    - If country is missing on one side, use bbox inference to fill before comparing.
    """
    # Sort by population descending to keep the largest first
    sorted_places = sorted(places, key=lambda r: (int(r.get("population") or 0)), reverse=True)

    seen: List[Dict] = []
    for candidate in sorted_places:
        name_key = _normalize_name(str(candidate.get("name", "")))
        cand_country = str(candidate.get("country", "")).upper()
        cand_lat = float(candidate["latitude"])  # type: ignore[index]
        cand_lon = float(candidate["longitude"])  # type: ignore[index]

        merged = False
        for idx, kept in enumerate(seen):
            if _normalize_name(str(kept.get("name", ""))) != name_key:
                continue
            kept_country = str(kept.get("country", "")).upper()
            d = _haversine_km(cand_lat, cand_lon, float(kept["latitude"]), float(kept["longitude"]))
            if d > distance_km_threshold:
                continue

            # We consider these duplicates; decide which to keep and how to set country
            cand_source = str(candidate.get("source", "")).lower()
            kept_source = str(kept.get("source", "")).lower()

            # Infer countries using boundary lookup with region-allowed constraint; fallback to bbox heuristic
            cand_country_inferred = (
                infer_country_iso_a2(cand_lat, cand_lon, allowed=allowed_countries)
                or infer_country_by_bbox(cand_lat, cand_lon)
                or cand_country
            )
            kept_country_inferred = (
                infer_country_iso_a2(float(kept["latitude"]), float(kept["longitude"]), allowed=allowed_countries)
                or infer_country_by_bbox(float(kept["latitude"]), float(kept["longitude"]))
                or kept_country
            )

            prefer_candidate = False
            # Prefer GeoNames over OSM
            if kept_source != cand_source:
                if cand_source == "geonames":
                    prefer_candidate = True
                elif kept_source == "geonames":
                    prefer_candidate = False
                else:
                    prefer_candidate = int(candidate.get("population") or 0) > int(kept.get("population") or 0)
            else:
                # Same source: choose higher population
                prefer_candidate = int(candidate.get("population") or 0) > int(kept.get("population") or 0)

            # Determine the country to keep, prioritizing boundary/bbox-consistent over source tag
            resolved_country = ""
            if cand_country_inferred and kept_country_inferred:
                if cand_country_inferred == kept_country_inferred:
                    resolved_country = cand_country_inferred
                else:
                    # Disagreement; prefer boundary-inferred for the preferred record
                    resolved_country = cand_country_inferred if prefer_candidate else kept_country_inferred
            else:
                resolved_country = cand_country_inferred or kept_country_inferred or (str(candidate.get("country", "")).upper() if prefer_candidate else kept_country)

            if prefer_candidate:
                new_kept = {**candidate}
                if resolved_country:
                    new_kept["country"] = resolved_country
                seen[idx] = new_kept
            else:
                if resolved_country:
                    kept["country"] = resolved_country
                # keep existing 'kept'
            merged = True
            break

        if not merged:
            # Ensure candidate has a sensible country if missing
            if not cand_country:
                inferred = infer_country_iso_a2(cand_lat, cand_lon, allowed=allowed_countries) or infer_country_by_bbox(cand_lat, cand_lon)
                if inferred:
                    candidate = {**candidate, "country": inferred}
            seen.append(candidate)

    return seen
