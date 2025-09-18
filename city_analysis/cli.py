from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List
import logging

from dotenv import load_dotenv

from .config import ALPINE_COUNTRIES, DEFAULT_MIN_POPULATION, DEFAULT_REQUIRE_OSM_POPULATION, load_region_settings, load_region_settings_from_yaml
from .geometry import default_alps_polygon, load_perimeter, polygon_bounds
from .perimeter_loader import resolve_region_perimeter
from .geonames import fetch_geonames_cities
from .overpass import fetch_overpass_bbox_tiled
from .normalize import filter_within_perimeter, dedupe_places, enforce_min_population
from .io_utils import write_csv, write_geojson, read_csv_records
from .analysis import top_n_by_population, summarize
from .country_filters import filter_excluded_countries, fill_missing_country
from .distance import add_distance_to_perimeter_km
from .elevation import enrich_places_with_elevation
from .map_utils import save_map, save_country_map
from .hospital_check import enrich_records_with_hospital_presence, enrich_records_with_hospital_presence_osm
from .airport_check import enrich_records_with_nearest_airport, enrich_records_with_nearest_airport_offline


def parse_args() -> argparse.Namespace:
    # Load .env before reading environment defaults
    load_dotenv()

    parser = argparse.ArgumentParser(description="Analyze populations and coordinates of cities in/near a mountain region.")
    parser.add_argument("--region", type=str, default=os.getenv("REGION", "alps"), help="Region slug to analyze (e.g., alps, pyrenees)")
    parser.add_argument("--region-config", type=str, default=os.getenv("REGION_CONFIG"), help="Optional YAML file defining region settings")
    parser.add_argument("--geonames-username", default=os.getenv("GEONAMES_USERNAME"), help="GeoNames username (or set GEONAMES_USERNAME env var)")
    parser.add_argument("--min-population", type=int, default=DEFAULT_MIN_POPULATION, help="Minimum population threshold for GeoNames and final output")
    parser.add_argument("--countries", nargs="*", default=None, help="Country codes to include; defaults to region settings")
    parser.add_argument("--perimeter", type=str, help="Path to region perimeter GeoJSON (FeatureCollection/Feature/Geometry). Overrides region settings.")
    # Villages now included by default; keep arg for backward-compat but ignore
    parser.add_argument("--require-osm-population", action="store_true", default=DEFAULT_REQUIRE_OSM_POPULATION, help=argparse.SUPPRESS)
    parser.add_argument("--include-villages", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--tile-size", type=float, default=1.0, help="Tile size in degrees for Overpass tiling")
    parser.add_argument("--out-dir", type=str, default="outputs", help="Directory to write outputs")
    parser.add_argument("--cache-dir", type=str, default="outputs/cache", help="Directory to cache intermediate fetches (tiles, etc.)")
    parser.add_argument("--top", type=int, default=20, help="Show top-N by population in console")
    parser.add_argument("--google-api-key", default=os.getenv("GOOGLE_API_KEY"), help="Google Elevation API key (or set GOOGLE_API_KEY env var)")
    parser.add_argument("--elevation-batch-size", type=int, default=100, help="Batch size for elevation API requests")
    parser.add_argument("--skip-elevation", action="store_true", help="Skip elevation enrichment (use only OSM/GeoNames data)")

    # Hospital presence check (optional)
    # Hospitals always enriched via OSM by default; suppress CLI toggles
    parser.add_argument("--check-hospitals", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--hospital-mode", type=str, choices=["osm", "openai", "hybrid"], default=os.getenv("HOSPITAL_MODE", "osm"), help=argparse.SUPPRESS)
    parser.add_argument("--hospital-radius-km", type=float, default=float(os.getenv("HOSPITAL_RADIUS_KM", "3.0")), help="Radius in km around city centroid to consider OSM hospitals (default 3.0)")
    parser.add_argument("--hospital-tile-size", type=float, default=float(os.getenv("HOSPITAL_TILE_SIZE_DEG", "1.0")), help="Overpass tile size in degrees for hospital fetch (default 1.0)")
    parser.add_argument("--hospital-no-openai-fallback", action="store_true", help="In hybrid mode, disable OpenAI fallback (OSM only)")
    parser.add_argument("--openai-model", type=str, default=os.getenv("OPENAI_MODEL", "gpt-5"), help="OpenAI model to use for hospital/airport checks when enabled")
    parser.add_argument("--openai-timeout", type=float, default=float(os.getenv("OPENAI_TIMEOUT", "60")), help="Per-request timeout (seconds) for OpenAI when enabled")

    # Map generation options
    parser.add_argument("--make-map", action="store_true", help="Generate interactive HTML map alongside CSV/GeoJSON")
    parser.add_argument("--map-file", type=str, default=None, help="Path for HTML map output (default: <out-dir>/<region>_cities_map.html)")
    # If omitted, we'll default to the region's configured tiles (settings.map_tiles)
    parser.add_argument("--map-tiles", type=str, default=None, help="Folium tiles name or URL (defaults to region setting)")

    # Airport nearest + driving distance/time (optional)
    # Airports always enriched via offline dataset by default; suppress toggles
    parser.add_argument("--check-airports", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--airports-use-openai", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--airports-dataset", type=str, default=os.getenv("AIRPORTS_DATASET", None), help="Path to OurAirports CSV; if omitted, auto-download and cache")
    parser.add_argument("--airports-topk", type=int, default=int(os.getenv("AIRPORTS_TOPK", "3")), help="Top-K nearest airports to consider for OSRM refinement (offline mode)")
    parser.add_argument("--airports-max-radius-km", type=float, default=float(os.getenv("AIRPORTS_MAX_RADIUS_KM", "400")), help="Max crow-flies radius to attempt OSRM driving (offline mode)")
    parser.add_argument("--osrm-base-url", type=str, default=os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org"), help="Base URL for OSRM routing service")
    parser.add_argument("--airports-limit", type=int, default=None, help="Limit number of records to process for airport enrichment (useful for testing)")
    parser.add_argument("--airports-resume-missing", action="store_true", help="Only process rows missing airport name or with airport_error; keep existing successes")
    parser.add_argument("--airports-max-retries", type=int, default=int(os.getenv("AIRPORTS_MAX_RETRIES", "2")), help="Max retries for OpenAI airport lookup")
    parser.add_argument("--airports-initial-backoff", type=float, default=float(os.getenv("AIRPORTS_INITIAL_BACKOFF", "2.0")), help="Initial backoff seconds before retry")
    parser.add_argument("--airports-backoff-multiplier", type=float, default=float(os.getenv("AIRPORTS_BACKOFF_MULTIPLIER", "2.0")), help="Backoff multiplier between retries")
    parser.add_argument("--airports-jitter", type=float, default=float(os.getenv("AIRPORTS_JITTER", "0.5")), help="Jitter seconds added/subtracted to backoff")

    # Second map style (country-colored, population-sized)
    parser.add_argument("--make-country-map", action="store_true", help="Generate country-colored, population-sized map")
    parser.add_argument("--country-map-file", type=str, default=None, help="Path for second map HTML (default: <out-dir>/<region>_cities_country_map.html)")

    # Build map directly from an existing CSV (skips fetching/processing)
    parser.add_argument("--from-csv", type=str, default=None, help="Path to an existing CSV of cities to build a map from")
    # Pipeline staging / checkpointing
    parser.add_argument("--stage", type=str, choices=[
        "fetch", "filter", "dedupe", "enrich_elevation", "enrich_hospitals", "enrich_airports", "maps", "all"
    ], default=os.getenv("STAGE", "all"), help="Run a specific pipeline stage or 'all'")
    parser.add_argument("--resume", action="store_true", help="Resume from cached tiles/intermediate files when available")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    # Configure logging for better visibility
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Resolve region settings
    if args.region_config:
        settings = load_region_settings_from_yaml(args.region_config)
    else:
        settings = load_region_settings(args.region)

    # Fast path: Build map(s) directly from an existing CSV
    if args.from_csv:
        records = read_csv_records(args.from_csv)
        out_dir = Path(args.out_dir) / settings.slug
        out_dir.mkdir(parents=True, exist_ok=True)

        # Compute perimeter and bbox for optional enrichments that need it
        if args.perimeter:
            perimeter = load_perimeter(args.perimeter)
        else:
            perimeter = resolve_region_perimeter(settings)
        bbox = polygon_bounds(perimeter)

        # Optionally enrich CSV with hospital presence before building maps
        if args.check_hospitals:
            if args.hospital_mode == "openai":
                print("Checking hospital presence via OpenAI (explicitly enabled)", file=sys.stderr)
                records = enrich_records_with_hospital_presence(
                    records,
                    model=args.openai_model,
                    request_timeout=args.openai_timeout,
                )
            else:
                print("Checking hospital presence via OSM (default)", file=sys.stderr)
                records = enrich_records_with_hospital_presence_osm(
                    records,
                    perimeter_bbox=bbox if 'bbox' in locals() else None,
                    radius_km=args.hospital_radius_km,
                    tile_size_deg=args.hospital_tile_size,
                    sleep_between_tiles=0.5,
                    fallback_to_openai=(args.hospital_mode == "hybrid" and not args.hospital_no_openai_fallback),
                    model=args.openai_model,
                    request_timeout=args.openai_timeout,
                    osrm_base_url=args.osrm_base_url,
                )
            csv_path = out_dir / f"{settings.slug}_cities.csv"
            write_csv(csv_path, records)
            print(f"Wrote CSV with hospital columns to {csv_path}")
        # Optionally enrich CSV with nearest airport and driving info
        if args.check_airports:
            print("Finding nearest international airports and driving metrics...", file=sys.stderr)
            if args.airports_use_openai:
                print("Using OpenAI mode (explicitly opted in)", file=sys.stderr)
                records = enrich_records_with_nearest_airport(
                    records,
                    model=args.openai_model,
                    request_timeout=args.openai_timeout,
                    osrm_base_url=args.osrm_base_url,
                    max_retries=args.airports_max_retries,
                    initial_backoff_seconds=args.airports_initial_backoff,
                    backoff_multiplier=args.airports_backoff_multiplier,
                    jitter_seconds=args.airports_jitter,
                    limit=args.airports_limit,
                    resume_missing_only=args.airports_resume_missing,
                )
            else:
                print("Using offline dataset mode (default; no OpenAI)", file=sys.stderr)
                records = enrich_records_with_nearest_airport_offline(
                    records,
                    dataset_csv=args.airports_dataset,
                    osrm_base_url=args.osrm_base_url,
                    topk=args.airports_topk,
                    max_radius_km=args.airports_max_radius_km,
                    limit=args.airports_limit,
                    resume_missing_only=args.airports_resume_missing,
                )
            csv_path = out_dir / f"{settings.slug}_cities.csv"
            write_csv(csv_path, records)
            print(f"Wrote CSV with airport and driving columns to {csv_path}")
        if args.make_map:
            map_path = Path(args.map_file) if args.map_file else (out_dir / f"{settings.slug}_cities_map.html")
            save_map(records, map_path, tiles=(args.map_tiles or settings.map_tiles))
            print(f"Wrote interactive map to {map_path}")
        if args.make_country_map:
            country_map_path = Path(args.country_map_file) if args.country_map_file else (out_dir / f"{settings.slug}_cities_country_map.html")
            save_country_map(records, country_map_path, tiles=(args.map_tiles or settings.map_tiles))
            print(f"Wrote country-colored map to {country_map_path}")
        # If neither flag was given, default to generating both maps from CSV for convenience
        if not args.make_map and not args.make_country_map:
            map_path = out_dir / f"{settings.slug}_cities_map.html"
            save_map(records, map_path, tiles=(args.map_tiles or settings.map_tiles))
            print(f"Wrote interactive map to {map_path}")
            country_map_path = out_dir / f"{settings.slug}_cities_country_map.html"
            save_country_map(records, country_map_path, tiles=(args.map_tiles or settings.map_tiles))
            print(f"Wrote country-colored map to {country_map_path}")
        return

    if not args.geonames_username:
        print("Error: GeoNames username is required. Set GEONAMES_USERNAME in your environment or use --geonames-username.", file=sys.stderr)
        sys.exit(1)

    # Load or default perimeter
    if args.perimeter:
        perimeter = load_perimeter(args.perimeter)
    else:
        perimeter = resolve_region_perimeter(settings)

    # Build Overpass tiles using bbox from perimeter
    bbox = polygon_bounds(perimeter)
    # Always include villages by default
    place_types = ("city", "town", "village")

    # Fetch data
    geonames_records: List[dict] = []
    if args.geonames_username:
        try:
            geonames_records = fetch_geonames_cities(
                countries=(args.countries or settings.countries),
                min_population=(args.min_population or settings.min_population),
                username=args.geonames_username,
            )
        except Exception as e:
            print(f"Error: GeoNames fetch failed ({e}). Aborting run because GeoNames is required.", file=sys.stderr)
            sys.exit(1)

    # Stage: fetch
    out_dir = Path(args.out_dir) / settings.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    stage_fetch_json = out_dir / "stage_fetch_combined.json"
    stage_filtered_json = out_dir / "stage_filtered.json"
    stage_deduped_json = out_dir / "stage_deduped.json"
    stage_enriched_elev_json = out_dir / "stage_enriched_elevation.json"
    stage_enriched_hosp_json = out_dir / "stage_enriched_hospitals.json"
    stage_enriched_air_json = out_dir / "stage_enriched_airports.json"

    if args.stage in ("fetch", "all"):
        osm_records = fetch_overpass_bbox_tiled(
            bbox=bbox,
            place_types=place_types,
            require_population_tag=args.require_osm_population,
            tile_size_deg=args.tile_size,
            cache_dir=str(Path(args.cache_dir)),
            region_slug=settings.slug,
            resume=args.resume,
        )
        combined = geonames_records + osm_records
        # Save fetch stage
        write_geojson(stage_fetch_json, combined)
        if args.stage == "fetch":
            # Stop after completing this stage unless running full pipeline
            return
    else:
        # Load from previous stage
        if stage_fetch_json.exists():
            combined = read_csv_records(stage_fetch_json) if str(stage_fetch_json).endswith(".csv") else []
            # Allow GeoJSON as JSON list of features conversion
            try:
                import json as _json
                data = _json.loads(stage_fetch_json.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("type") == "FeatureCollection":
                    feats = data.get("features", [])
                    combined = []
                    for f in feats:
                        props = f.get("properties", {})
                        geom = f.get("geometry", {})
                        if geom and geom.get("type") == "Point":
                            coords = geom.get("coordinates", [None, None])
                            props["longitude"], props["latitude"] = coords[0], coords[1]
                        combined.append(props)
            except Exception:
                combined = []
        else:
            print("Error: fetch stage output missing; run with --stage fetch first.", file=sys.stderr)
            sys.exit(2)

    # At this point `combined` is already set either from fresh fetch (fetch stage)
    # or loaded from the previous stage file. Do not recompute here.

    # Exclude configured countries (region-aware), fill missing countries using boundary lookup limited to region
    # Stage: filter
    if args.stage in ("filter", "all"):
        combined = filter_excluded_countries(combined, excluded_codes=(settings.excluded_countries or []))
        combined = fill_missing_country(combined, allowed_countries=(args.countries or settings.countries))
        filtered = filter_within_perimeter(combined, perimeter=perimeter)
        filtered = enforce_min_population(filtered, min_population=(args.min_population or settings.min_population))
        write_geojson(stage_filtered_json, filtered)
        if args.stage == "filter":
            return
    else:
        try:
            import json as _json
            data = _json.loads(stage_filtered_json.read_text(encoding="utf-8"))
            feats = data.get("features", [])
            filtered = []
            for f in feats:
                props = f.get("properties", {})
                geom = f.get("geometry", {})
                if geom and geom.get("type") == "Point":
                    coords = geom.get("coordinates", [None, None])
                    props["longitude"], props["latitude"] = coords[0], coords[1]
                filtered.append(props)
        except Exception:
            print("Error: filter stage output missing/unreadable; run with --stage filter first.", file=sys.stderr)
            sys.exit(2)

    # Enforce min population on merged results and dedupe
    # Stage: dedupe
    if args.stage in ("dedupe", "all"):
        deduped = dedupe_places(filtered, allowed_countries=(args.countries or settings.countries))
        write_geojson(stage_deduped_json, deduped)
        if args.stage == "dedupe":
            return
    else:
        try:
            import json as _json
            data = _json.loads(stage_deduped_json.read_text(encoding="utf-8"))
            feats = data.get("features", [])
            deduped = []
            for f in feats:
                props = f.get("properties", {})
                geom = f.get("geometry", {})
                if geom and geom.get("type") == "Point":
                    coords = geom.get("coordinates", [None, None])
                    props["longitude"], props["latitude"] = coords[0], coords[1]
                deduped.append(props)
        except Exception:
            print("Error: dedupe stage output missing/unreadable; run with --stage dedupe first.", file=sys.stderr)
            sys.exit(2)

    # Add distance to region perimeter
    enriched = add_distance_to_perimeter_km(deduped, perimeter=perimeter, region_slug=settings.slug)

    # Stage: enrich_elevation
    if args.stage in ("enrich_elevation", "all"):
        if not args.skip_elevation:
            print("Enriching places with elevation data...", file=sys.stderr)
            enriched = enrich_places_with_elevation(
                enriched,
                google_api_key=args.google_api_key,
                batch_size=args.elevation_batch_size
            )
        else:
            print("Skipping elevation enrichment (using only OSM/GeoNames data)", file=sys.stderr)
        write_geojson(stage_enriched_elev_json, enriched)
        if args.stage == "enrich_elevation":
            return
    else:
        try:
            import json as _json
            data = _json.loads(stage_enriched_elev_json.read_text(encoding="utf-8"))
            feats = data.get("features", [])
            enriched = []
            for f in feats:
                props = f.get("properties", {})
                geom = f.get("geometry", {})
                if geom and geom.get("type") == "Point":
                    coords = geom.get("coordinates", [None, None])
                    props["longitude"], props["latitude"] = coords[0], coords[1]
                enriched.append(props)
        except Exception:
            print("Error: enrich_elevation stage output missing/unreadable; run that stage first.", file=sys.stderr)
            sys.exit(2)

    # Optional: Hospital presence check
    # Always enrich with hospital presence via OSM by default
    # Stage: enrich_hospitals
    if args.stage in ("enrich_hospitals", "all"):
        print("Checking hospital presence via OSM (default)", file=sys.stderr)
        enriched = enrich_records_with_hospital_presence_osm(
            enriched,
            perimeter_bbox=bbox,
            radius_km=args.hospital_radius_km,
            tile_size_deg=args.hospital_tile_size,
            sleep_between_tiles=0.5,
            fallback_to_openai=False,
            model=args.openai_model,
            request_timeout=args.openai_timeout,
            osrm_base_url=args.osrm_base_url,
            cache_dir=str(Path(args.cache_dir)),
            region_slug=settings.slug,
            resume=args.resume,
        )
        write_geojson(stage_enriched_hosp_json, enriched)
        if args.stage == "enrich_hospitals":
            return
    else:
        try:
            import json as _json
            data = _json.loads(stage_enriched_hosp_json.read_text(encoding="utf-8"))
            feats = data.get("features", [])
            enriched = []
            for f in feats:
                props = f.get("properties", {})
                geom = f.get("geometry", {})
                if geom and geom.get("type") == "Point":
                    coords = geom.get("coordinates", [None, None])
                    props["longitude"], props["latitude"] = coords[0], coords[1]
                enriched.append(props)
        except Exception:
            print("Error: enrich_hospitals stage output missing/unreadable; run that stage first.", file=sys.stderr)
            sys.exit(2)

    # Optional: Nearest international airport + driving time/distance
    # Always enrich with nearest airport via offline dataset by default
    # Stage: enrich_airports
    if args.stage in ("enrich_airports", "all"):
        print("Finding nearest international airports and driving metrics...", file=sys.stderr)
        print("Using offline dataset mode (default; no OpenAI)", file=sys.stderr)
        enriched = enrich_records_with_nearest_airport_offline(
            enriched,
            dataset_csv=args.airports_dataset,
            osrm_base_url=args.osrm_base_url,
            topk=args.airports_topk,
            max_radius_km=args.airports_max_radius_km or 1000.0,
            limit=args.airports_limit,
            resume_missing_only=args.airports_resume_missing,
        )
        write_geojson(stage_enriched_air_json, enriched)
        if args.stage == "enrich_airports":
            return
    else:
        try:
            import json as _json
            data = _json.loads(stage_enriched_air_json.read_text(encoding="utf-8"))
            feats = data.get("features", [])
            enriched = []
            for f in feats:
                props = f.get("properties", {})
                geom = f.get("geometry", {})
                if geom and geom.get("type") == "Point":
                    coords = geom.get("coordinates", [None, None])
                    props["longitude"], props["latitude"] = coords[0], coords[1]
                enriched.append(props)
        except Exception:
            print("Error: enrich_airports stage output missing/unreadable; run that stage first.", file=sys.stderr)
            sys.exit(2)

    # Ensure output directory
    out_dir = Path(args.out_dir) / settings.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write outputs
    write_csv(out_dir / f"{settings.slug}_cities.csv", enriched)
    write_geojson(out_dir / f"{settings.slug}_cities.geojson", enriched)

    # Optionally write interactive maps
    # Stage: maps
    if args.stage in ("maps", "all") and args.make_map:
        map_path = Path(args.map_file) if args.map_file else (out_dir / f"{settings.slug}_cities_map.html")
        save_map(enriched, map_path, tiles=(args.map_tiles or settings.map_tiles))
        print(f"Wrote interactive map to {map_path}")
    if args.stage in ("maps", "all") and args.make_country_map:
        country_map_path = Path(args.country_map_file) if args.country_map_file else (out_dir / f"{settings.slug}_cities_country_map.html")
        save_country_map(enriched, country_map_path, tiles=(args.map_tiles or settings.map_tiles))
        print(f"Wrote country-colored map to {country_map_path}")

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
        print(f"  {r['name']} ({r.get('country','')}) — pop {r.get('population', 0):,} @ ({r['latitude']:.4f},{r['longitude']:.4f}) [{r['source']}]" +
              f"{elevation_info}, {r.get('distance_km_to_perimeter')} km to {settings.name}")


if __name__ == "__main__":
    main()
