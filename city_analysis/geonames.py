from __future__ import annotations

import time
from typing import Dict, Iterable, List

import requests

GEONAMES_ENDPOINT = "http://api.geonames.org/searchJSON"
DEFAULT_HEADERS = {
    "User-Agent": "city-analysis-alps/0.1 (contact: your-email@example.com)",
}


def fetch_geonames_cities(
    countries: Iterable[str],
    min_population: int,
    username: str,
    max_rows: int = 1000,
    request_pause_seconds: float = 1.0,
) -> List[Dict]:
    """Fetch cities from GeoNames for specified countries and minimum population.

    This uses the searchJSON endpoint for featureClass=P (populated places) and
    orders by population. It paginates through results.

    Args:
        countries: ISO 3166-1 alpha-2 codes to query, e.g. ["AT", "CH", ...].
        min_population: Minimum population threshold to apply server-side.
        username: GeoNames username (register at geonames.org).
        max_rows: Page size per request (GeoNames max is 1000).
        request_pause_seconds: Throttle between requests to be polite.

    Returns:
        List of place dicts with keys: name, country, latitude, longitude, population, source
    """
    combined: List[Dict] = []
    for country in countries:
        start_row = 0
        while True:
            params = {
                "featureClass": "P",
                "country": country,
                "orderby": "population",
                "maxRows": max_rows,
                "startRow": start_row,
                "username": username,
                "minPopulation": min_population,
            }
            resp = requests.get(GEONAMES_ENDPOINT, params=params, headers=DEFAULT_HEADERS, timeout=30)
            resp.raise_for_status()
            # Ensure proper UTF-8 encoding
            resp.encoding = 'utf-8'
            payload = resp.json()
            total = int(payload.get("totalResultsCount", 0))
            geonames = payload.get("geonames", [])

            for item in geonames:
                try:
                    name = item.get("name") or item.get("toponymName")
                    country_code = item.get("countryCode")
                    lat = float(item.get("lat"))
                    lng = float(item.get("lng"))
                    population = int(item.get("population") or 0)
                    # Extract elevation if available
                    elevation = item.get("elevation")
                    if elevation is not None:
                        try:
                            elevation = float(elevation)
                        except (ValueError, TypeError):
                            elevation = None
                    
                    if not name or not country_code:
                        continue
                    combined.append(
                        {
                            "name": name,
                            "country": country_code,
                            "latitude": lat,
                            "longitude": lng,
                            "population": population,
                            "elevation": elevation,
                            "source": "geonames",
                        }
                    )
                except Exception:
                    # Skip malformed entries gracefully
                    continue

            start_row += max_rows
            if start_row >= total or not geonames:
                break
            time.sleep(request_pause_seconds)
    return combined
