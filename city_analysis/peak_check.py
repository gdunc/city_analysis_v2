from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from dataclasses import dataclass
from tqdm import tqdm

from .overpass import fetch_overpass_peaks_bbox_tiled


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371.0
    return r * c


def _load_peaks_for_bbox(
    bbox: Tuple[float, float, float, float],
    *,
    tile_size_deg: float = 1.0,
    sleep_between: float = 0.5,
    cache_dir: Optional[str] = None,
    region_slug: Optional[str] = None,
    resume: bool = False,
) -> List[Dict]:
    return fetch_overpass_peaks_bbox_tiled(
        bbox=bbox,
        tile_size_deg=tile_size_deg,
        sleep_between=sleep_between,
        cache_dir=cache_dir,
        region_slug=region_slug,
        resume=resume,
    )


def enrich_records_with_nearby_higher_peaks(
    records: Iterable[Dict],
    *,
    perimeter_bbox: Optional[Tuple[float, float, float, float]] = None,
    radius_km: float = 30.0,
    min_height_diff_m: float = 1200.0,
    tile_size_deg: float = 1.0,
    sleep_between_tiles: float = 0.5,
    cache_dir: Optional[str] = None,
    region_slug: Optional[str] = None,
    resume: bool = False,
) -> List[Dict]:
    """
    For each city record, find OSM peaks within radius_km whose elevation is at least
    min_height_diff_m higher than the city's elevation.

    Adds fields:
      - peaks_higher1200_within30km_count (int)
      - peaks_higher1200_within30km_names (str; semicolon-separated)
      - peaks_higher1200_within30km (list[dict]) with name, latitude, longitude, elevation
    (Field names match defaults for 30km/1200m but apply generically based on params.)
    """
    items = list(records)
    if not items:
        return items

    # Load peaks once for the whole perimeter bbox; if not provided, derive a bbox from data
    if perimeter_bbox is None:
        lats = [float(r.get("latitude")) for r in items if r.get("latitude") is not None]
        lons = [float(r.get("longitude")) for r in items if r.get("longitude") is not None]
        if not lats or not lons:
            peaks: List[Dict] = []
        else:
            south, north = min(lats) - 1.0, max(lats) + 1.0
            west, east = min(lons) - 1.0, max(lons) + 1.0
            peaks = _load_peaks_for_bbox(
                (south, west, north, east),
                tile_size_deg=tile_size_deg,
                sleep_between=sleep_between_tiles,
                cache_dir=cache_dir,
                region_slug=region_slug,
                resume=resume,
            )
    else:
        peaks = _load_peaks_for_bbox(
            perimeter_bbox,
            tile_size_deg=tile_size_deg,
            sleep_between=sleep_between_tiles,
            cache_dir=cache_dir,
            region_slug=region_slug,
            resume=resume,
        )

    # Pre-index peaks for coarse filtering by degree window around cities
    deg_radius = max(0.2, radius_km / 111.0)  # ~1 deg ~111 km near equator

    enriched: List[Dict] = []
    for r in tqdm(items, desc="Finding nearby higher peaks", unit="city"):
        try:
            lat0 = float(r.get("latitude"))
            lon0 = float(r.get("longitude"))
        except Exception:
            enriched.append({**r})
            continue

        elev0 = None
        try:
            if r.get("elevation") is not None:
                elev0 = float(r.get("elevation"))
        except Exception:
            elev0 = None

        matches: List[Dict] = []
        names: List[str] = []
        if peaks:
            for p in peaks:
                try:
                    plat = float(p.get("latitude"))
                    plon = float(p.get("longitude"))
                except Exception:
                    continue
                if abs(plat - lat0) > deg_radius or abs(plon - lon0) > deg_radius:
                    continue
                d = _haversine_km(lat0, lon0, plat, plon)
                if d > radius_km:
                    continue
                p_elev = p.get("elevation")
                try:
                    p_elev_val = float(p_elev) if p_elev is not None else None
                except Exception:
                    p_elev_val = None
                # Only count if we know both elevations and peak is sufficiently higher
                if elev0 is not None and p_elev_val is not None and (p_elev_val - elev0) >= min_height_diff_m:
                    nm = str(p.get("name") or "")
                    names.append(nm)
                    matches.append({
                        "name": nm,
                        "latitude": plat,
                        "longitude": plon,
                        "elevation": p_elev_val,
                        "distance_km": round(d, 3),
                    })

        new_r = dict(r)
        count_field = "peaks_higher1200_within30km_count"
        names_field = "peaks_higher1200_within30km_names"
        list_field = "peaks_higher1200_within30km"
        new_r[count_field] = len(matches)
        new_r[names_field] = "; ".join([n for n in names if n]) if matches else ""
        new_r[list_field] = matches
        enriched.append(new_r)

    return enriched


