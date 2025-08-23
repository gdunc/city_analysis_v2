from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List
import logging

from dotenv import load_dotenv

from .config import ALPINE_COUNTRIES, DEFAULT_MIN_POPULATION, DEFAULT_REQUIRE_OSM_POPULATION
from .geometry import default_alps_polygon, load_perimeter, polygon_bounds
from .geonames import fetch_geonames_cities
from .overpass import fetch_overpass_bbox_tiled
from .normalize import filter_within_perimeter, dedupe_places, enforce_min_population
from .io_utils import write_csv, write_geojson, write_html_map
from .analysis import top_n_by_population, summarize
from .country_filters import filter_excluded_countries, fill_missing_country
from .distance import add_distance_to_perimeter_km
from .elevation import enrich_places_with_elevation


def parse_args() -> argparse.Namespace:
    # Load .env before reading environment defaults
    load_dotenv()

    parser = argparse.ArgumentParser(description="Analyze populations and coordinates of cities in/near the Alps.")
    parser.add_argument("--geonames-username", default=os.getenv("GEONAMES_USERNAME"), help="GeoNames username (or set GEONAMES_USERNAME env var)")
    parser.add_argument("--min-population", type=int, default=DEFAULT_MIN_POPULATION, help="Minimum population threshold for GeoNames and final output")
    parser.add_argument("--countries", nargs="*", default=ALPINE_COUNTRIES, help="Country codes to include (default: Alpine countries)")
    parser.add_argument("--perimeter", type=str, help="Path to Alpine perimeter GeoJSON (FeatureCollection/Feature/Geometry). If omitted, use a default bbox.")
    parser.add_argument("--require-osm-population", action="store_true", default=DEFAULT_REQUIRE_OSM_POPULATION, help="Only include OSM places that have a population tag")
    parser.add_argument("--include-villages", action="store_true", help="Include OSM places with place=village in addition to city,town")
    parser.add_argument("--tile-size", type=float, default=1.0, help="Tile size in degrees for Overpass tiling")
    parser.add_argument("--out-dir", type=str, default="outputs", help="Directory to write outputs")
    parser.add_argument("--top", type=int, default=20, help="Show top-N by population in console")
    parser.add_argument("--google-api-key", default=os.getenv("GOOGLE_API_KEY"), help="Google Elevation API key (or set GOOGLE_API_KEY env var)")
    parser.add_argument("--elevation-batch-size", type=int, default=100, help="Batch size for elevation API requests")
    parser.add_argument("--skip-elevation", action="store_true", help="Skip elevation enrichment (use only OSM/GeoNames data)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    # Configure logging for better visibility
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if not args.geonames_username:
        print("Note: GeoNames username missing; proceeding with OSM only.", file=sys.stderr)

    # Load or default perimeter
    if args.perimeter:
        perimeter = load_perimeter(args.perimeter)
    else:
        perimeter = default_alps_polygon()

    # Build Overpass tiles using bbox from perimeter
    bbox = polygon_bounds(perimeter)
    place_types = ("city", "town", "village") if args.include_villages else ("city", "town")

    # Fetch data
    geonames_records: List[dict] = []
    if args.geonames_username:
        try:
            geonames_records = fetch_geonames_cities(
                countries=args.countries,
                min_population=args.min_population,
                username=args.geonames_username,
            )
        except Exception as e:
            print(f"Warning: GeoNames fetch failed ({e}); continuing with OSM data only.", file=sys.stderr)
            geonames_records = []

    osm_records = fetch_overpass_bbox_tiled(
        bbox=bbox,
        place_types=place_types,
        require_population_tag=args.require_osm_population,
        tile_size_deg=args.tile_size,
    )

    # Combine
    combined: List[dict] = geonames_records + osm_records

    # Exclude CH/SI/LI, fill missing countries for AT/DE/FR/IT, filter within Alps
    combined = filter_excluded_countries(combined)
    combined = fill_missing_country(combined)
    filtered = filter_within_perimeter(combined, perimeter=perimeter)

    # Enforce min population on merged results and dedupe
    filtered = enforce_min_population(filtered, min_population=args.min_population)
    deduped = dedupe_places(filtered)

    # Add distance to Alps perimeter
    enriched = add_distance_to_perimeter_km(deduped, perimeter=perimeter)

    # Enrich with elevation data from multiple sources
    if not args.skip_elevation:
        print("Enriching places with elevation data...", file=sys.stderr)
        enriched = enrich_places_with_elevation(
            enriched,
            google_api_key=args.google_api_key,
            batch_size=args.elevation_batch_size
        )
    else:
        print("Skipping elevation enrichment (using only OSM/GeoNames data)", file=sys.stderr)

    # Ensure output directory
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write outputs
    write_csv(out_dir / "alps_cities.csv", enriched)
    write_geojson(out_dir / "alps_cities.geojson", enriched)
    write_html_map(out_dir / "alps_cities_map.html", enriched)

    # Console summary
    stats = summarize(enriched)
    print("Summary:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"\nTop {args.top} by population:")
    for r in top_n_by_population(enriched, n=args.top):
        elevation_info = ""
        if r.get('elevation') is not None:
            source_info = ""
            if r.get('elevation_source') and r.get('elevation_source') not in ['osm', 'geonames']:
                confidence = r.get('elevation_confidence', 0.0)
                source_info = f" [{r['elevation_source']}:{confidence:.1f}]"
            elevation_info = f", elev {r['elevation']}m{source_info}"
        print(f"  {r['name']} ({r.get('country','')}) — pop {r.get('population', 0):,} @ ({r['latitude']:.4f},{r['longitude']:.4f}) [{r['source']}]{elevation_info}, {r.get('distance_km_to_alps')} km to Alps")


if __name__ == "__main__":
    main()
