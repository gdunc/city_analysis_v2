# City Analysis v2 — Alpine Cities (Population + Coordinates)

Minimal toolchain to fetch and analyze cities in and near the Alps from GeoNames and OSM (Overpass), clipped to a comprehensive Alpine perimeter covering the full mountain range, with CSV/GeoJSON outputs and a console summary.

## Features
- **Population data** from GeoNames and OpenStreetMap
- **Coordinates** (latitude/longitude) for all places
- **Elevation data** where available (primarily from OSM)
- **Elevation enrichment** from multiple APIs (OpenTopoData, Google, Open-Elevation) for improved coverage
- **Distance to Alps** calculated for each place
- **Country filtering** with automatic country code inference
- **Population filtering** with configurable minimum thresholds

## Architecture (CTO-level overview)
- `city_analysis/geometry.py`: Perimeter handling (load GeoJSON, default Alps bbox, Overpass bbox conversion)
- `city_analysis/geonames.py`: GeoNames API client with pagination, normalized records
- `city_analysis/overpass.py`: Overpass QL builder and fetcher, normalized records (`place=city|town|village`)
- `city_analysis/normalize.py`: Perimeter filtering and fuzzy deduplication by name/country + distance
- `city_analysis/io_utils.py`: CSV and GeoJSON writers
- `city_analysis/analysis.py`: Summary metrics and top-N by population
- `city_analysis/cli.py`: CLI orchestration

## Data Sources
- **GeoNames**: Population data, coordinates, country codes (requires free account)
- **OpenStreetMap (OSM)**: Population data, coordinates, country codes, elevation data
- **Elevation**: Primarily from OSM `ele` tags, some from GeoNames where available

## Elevation Data Coverage
The tool now provides multi-source elevation enrichment to significantly improve coverage:

**Built-in Sources:**
- **OSM**: ~10-15% coverage (existing `ele` tags)
- **GeoNames**: ~5-10% coverage (geographic features)

**Enrichment Sources (when enabled):**
- **OpenTopoData**: Global 30m SRTM data, ~90-95% coverage
- **Google Elevation API**: High-accuracy global data, ~95%+ coverage (requires API key)
- **Open-Elevation**: Free alternative, ~85-90% coverage

**Expected Results:**
- **Without enrichment**: ~10-15% coverage (OSM + GeoNames only)
- **With enrichment**: ~90-95% coverage (all sources combined)

## Install
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration
- GeoNames requires a username (free). Set `GEONAMES_USERNAME` env var or pass `--geonames-username`.
- Google Elevation API (optional): Set `GOOGLE_API_KEY` env var or pass `--google-api-key` for enhanced elevation coverage.
- Perimeter: uses an included GeoJSON perimeter covering the full Alps. You can provide a custom polygon if desired.

## Usage
```bash
python -m city_analysis.cli --geonames-username YOUR_GEONAMES_USER --out-dir outputs
```
Optional flags:
- `--perimeter path/to/alpine_perimeter.geojson`
- `--countries AT CH FR IT DE SI LI` (defaults to Alpine countries)
- `--min-population 5000` (GeoNames server-side threshold; default)
- `--require-osm-population` (only include OSM places that tag `population`)
- `--include-villages` (include OSM place=village)
- `--tile-size 1.0` (degrees)
- `--top 20` (print top-N by population)
- `--google-api-key KEY` (Google Elevation API key for enhanced coverage)
- `--elevation-batch-size 100` (batch size for elevation API requests)
- `--skip-elevation` (skip elevation enrichment, use only OSM/GeoNames data)

Outputs in `outputs/`:
- `alps_cities.csv` - CSV with columns: name, country, latitude, longitude, population, elevation, elevation_source, elevation_confidence, source, distance_km_to_alps
- `alps_cities.geojson` - GeoJSON with all place data including elevation and distance metrics
- `alps_cities_map.html` - Interactive map of all places (Folium)

## Notes
- Licensing: GeoNames (CC BY 4.0), OSM (ODbL). Validate terms before redistribution.
- Population completeness varies, especially for OSM if `population` tag is missing.