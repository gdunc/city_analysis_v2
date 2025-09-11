# City Analysis v2 — Alpine Cities (Population + Coordinates)

Minimal toolchain to fetch and analyze cities in and near the Alps from GeoNames and OSM (Overpass), clipped to the Alpine perimeter, with CSV/GeoJSON outputs, optional elevation enrichment, hospital presence check, and interactive maps.

## Features
- **Population and coordinates** from GeoNames and OpenStreetMap
- **Elevation** from OSM/GeoNames, with optional multi-source enrichment (OpenTopoData, Google, Open‑Elevation)
- **Distance to Alps** computed for each place
- **Country filtering** with automatic country inference for missing codes
- **Population threshold** filtering
- **Interactive maps**:
  - Standard clustered map with color by population tier and a built-in client-side population filter UI
  - Country-colored, population-sized map
- **Hospital presence check (optional)** using OpenAI web search; adds `hospital_*` columns to CSV
- **Nearest international airport + driving (optional)** using OpenAI web search (trusted sources) and OSRM routing; adds `airport_*` and `driving_*` columns to CSV
- **CSV-to-map mode**: build maps directly from an existing CSV without refetching data

## Architecture (CTO-level overview)
- `city_analysis/geometry.py`: Perimeter handling (load GeoJSON, default Alps polygon/bbox, Overpass bbox conversion)
- `city_analysis/geonames.py`: GeoNames API client with pagination, normalized records
- `city_analysis/overpass.py`: Overpass QL builder and fetcher, normalized records (`place=city|town|village`)
- `city_analysis/normalize.py`: Perimeter filtering and deduplication by name + proximity with country resolution
- `city_analysis/distance.py`: Distance-to-perimeter computation (km) for each place
- `city_analysis/elevation.py`: Multi-source elevation enrichment (OpenTopoData → Google → Open‑Elevation)
- `city_analysis/country_filters.py`: Exclude CH/SI/LI; infer missing country by bbox for AT/DE/FR/IT
- `city_analysis/io_utils.py`: CSV and GeoJSON writers/readers
- `city_analysis/analysis.py`: Summary metrics and top-N by population
- `city_analysis/hospital_check.py`: Optional hospital presence enrichment via OpenAI web search
- `city_analysis/airport_check.py`: Optional nearest international airport enrichment via OpenAI web search + OSRM driving metrics
- `city_analysis/cli.py`: CLI orchestration
- `city_analysis/map_utils.py`: Folium map builders and savers (standard and country-colored)

## Data Sources
- **GeoNames**: Population, coordinates, country codes (requires free account)
- **OpenStreetMap (OSM)**: Population, coordinates, country codes, elevation tags (`ele`/`height`)
- **Elevation enrichment**: OpenTopoData, Google Elevation API, Open‑Elevation

## Elevation Data Coverage
Multi-source enrichment can significantly improve elevation coverage:

**Base sources:**
- OSM `ele`/`height` tags (limited coverage)
- GeoNames elevation (when present)

**Enrichment sources (optional):**
- OpenTopoData (free)
- Google Elevation API (API key required)
- Open‑Elevation (free)

## Install
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Configuration
- **GeoNames** username (free). Set `GEONAMES_USERNAME` env var or pass `--geonames-username`.
- **Google Elevation API** (optional): Set `GOOGLE_API_KEY` or pass `--google-api-key`.
- **OpenAI (optional)**: Set `OPENAI_API_KEY` for `--check-hospitals` and/or `--check-airports`. Optional `--openai-model` (default `gpt-5`) and `--openai-timeout`.
- **OSRM routing** (optional for airports): Default public server is used. Override with `--osrm-base-url` if you have your own OSRM instance.
- **Perimeter**: Provide a GeoJSON polygon/multipolygon of the Alps if available; otherwise, a realistic default polygon/bbox is used.

The CLI auto-loads a `.env` file if present (via `python-dotenv`). Example:
```bash
# .env
GEONAMES_USERNAME=your_user
GOOGLE_API_KEY=your_key   # optional
OPENAI_API_KEY=sk-...     # optional, for --check-hospitals
```
The repo includes an example perimeter file: `alps_perimeter.geojson`.

## Usage
```bash
python -m city_analysis.cli --geonames-username YOUR_GEONAMES_USER --out-dir outputs
```
Example using the included perimeter file and generating both maps:
```bash
python -m city_analysis.cli \
  --geonames-username YOUR_GEONAMES_USER \
  --perimeter alps_perimeter.geojson \
  --make-map \
  --make-country-map \
  --out-dir outputs
```

### CLI options: what they do and when to use them
- **--geonames-username USER**: Enables GeoNames fetching (more complete populations). Use when you want broader coverage; omit to run OSM-only (faster, fewer dependencies).
- **--perimeter FILE.geojson**: Custom Alpine perimeter or other region. Use to change study area; omit to use the built-in Alps polygon.
- **--countries CODES...**: Restrict GeoNames/OSM queries to listed country codes (default: AT FR IT DE; CH/SI/LI are removed later). Narrow for speed or broader for coverage.
- **--min-population N**: Minimum population filter for GeoNames and final output. Increase for performance/"bigger places" focus; decrease to include smaller towns (slower, noisier).
- **--require-osm-population**: Only include OSM places that explicitly have a `population` tag. Use for stricter data quality; omit to keep more places (may lack population values).
- **--include-villages**: Include OSM `place=village` in addition to `city`/`town`. Use to capture small settlements; omit to focus on larger urban areas.
- **--tile-size DEG**: Overpass tiling size in degrees. Decrease to avoid API timeouts on large queries (more requests); increase to reduce requests when area is small/reliable.
- **--out-dir PATH**: Where outputs are written. Use a dedicated directory when testing.
- **--top N**: How many top-by-population entries to print to the console. Cosmetic; no effect on outputs.

- **--google-api-key KEY**: Enables Google Elevation fallback (paid). Use for best elevation completeness; omit to avoid costs.
- **--elevation-batch-size N**: Batch size for elevation requests. Increase for speed if your quota allows; decrease if you hit rate limits.
- **--skip-elevation**: Skip elevation enrichment. Use to save time/cost when elevation is not needed.

- **--make-map**: Generate the standard clustered map. Include if you want a general-purpose interactive map.
- **--map-file PATH**: Custom path for the standard map HTML. Use to organize outputs.
- **--map-tiles NAME|URL**: Folium tileset. Change for visual preference or offline tiles.
- **--make-country-map**: Generate the country-colored, population-sized map. Include for comparative visual analysis by country.
- **--country-map-file PATH**: Custom path for the country map HTML.

- **--check-hospitals**: Use OpenAI web search to determine if each city has a hospital; writes `hospital_*` columns. Include when assessing local healthcare presence; omit to save API calls/time.
- **--openai-model MODEL**: OpenAI model for hospital/airport checks (default `gpt-5`). Use a different model if you have constraints or preferences.
- **--openai-timeout SECS**: Per-request timeout for OpenAI calls. Increase if you see timeouts; decrease to fail fast in testing.

- **--check-airports**: Use OpenAI web search to find the nearest international airport and compute driving via OSRM; writes `airport_*` and `driving_*` columns. Include for travel/accessibility analysis; omit to save API calls and routing requests.
- **--osrm-base-url URL**: OSRM routing endpoint. Use your own OSRM for reliability/privacy; omit to use the public server.
- **--airports-limit N**: Process only N rows for airport enrichment. Use for quick tests or cost control.
- **--airports-resume-missing**: Only process rows that are missing airport data or had prior errors. Use to resume/continue long runs without redoing successful rows.
- **--airports-max-retries N**: Max retries for OpenAI airport lookup. Increase to improve success under intermittent issues; decrease to save time.
- **--airports-initial-backoff SECS**: Initial backoff before retry. Increase when hitting rate limits.
- **--airports-backoff-multiplier X**: Exponential factor for backoff. Increase to be gentler under load.
- **--airports-jitter SECS**: Random jitter added/subtracted to backoff. Helps avoid thundering herd; keep small but non-zero.

- **--from-csv FILE.csv**: Build maps and/or run optional enrichments from an existing CSV (skips fetching/processing). Use to iterate quickly, resume runs, or enrich third-party CSVs.

### Generate interactive maps
Create a standard clustered map and/or a country-colored, population-sized map:
```bash
python -m city_analysis.cli --make-map --make-country-map --out-dir outputs
```
Specify a custom HTML path and tiles:
```bash
python -m city_analysis.cli --make-map \
  --map-file outputs/alps_cities_map.html \
  --map-tiles OpenStreetMap
```
Defaults:
- Standard map: `outputs/alps_cities_map.html`
- Country map: `outputs/alps_cities_country_map.html`

### Map details
- **Marker colors (standard map):**
  - darkred: ≥ 100,000
  - red: 50,000–99,999
  - orange: 20,000–49,999
  - green: 10,000–19,999
  - blue: < 10,000 or missing
- **Population filter UI:** Both map types include a simple control (top-left) to hide markers below a minimum population threshold, applied client-side without reloading.
- **Country map:** Markers are colored by country and sized by log-scaled population; each country is toggleable in the layer control.

### Build maps directly from an existing CSV
```bash
python -m city_analysis.cli --from-csv outputs/alps_cities.csv --make-map --make-country-map --out-dir outputs
```
If `--make-map`/`--make-country-map` are omitted with `--from-csv`, both maps are generated by default.

### Hospital presence check (optional)
Adds four columns to the CSV based on OpenAI web search:
- `hospital_in_city` ("yes"|"no")
- `hospital_confidence_pct` (0–100)
- `hospital_reasoning` (brief rationale + up to 3 links)
- `hospital_error` (error message if any)

Usage:
```bash
OPENAI_API_KEY=sk-... python -m city_analysis.cli --check-hospitals --out-dir outputs
```

### Nearest international airport + driving (optional)
Adds columns based on OpenAI web search (trusted sources only) and OSRM driving route:
- `airport_nearest_name`, `airport_nearest_iata`, `airport_nearest_icao`
- `airport_nearest_latitude`, `airport_nearest_longitude`
- `airport_confidence_pct` (0–100), `airport_reasoning` (brief rationale + links), `airport_error`
- `driving_km_to_airport`, `driving_time_minutes_to_airport`
- `driving_confidence_pct`, `driving_reasoning`, `driving_error`

Usage (from full pipeline results or any existing CSV):
```bash
OPENAI_API_KEY=sk-... python -m city_analysis.cli \
  --from-csv outputs/alps_cities.csv \
  --check-airports \
  --out-dir outputs \
  --openai-model gpt-5 \
  --openai-timeout 90
```

Controls:
- Limit for testing: `--airports-limit 5`
- Resume only rows missing airports or with prior errors: `--airports-resume-missing`
- Reliability: `--airports-max-retries`, `--airports-initial-backoff`, `--airports-backoff-multiplier`, `--airports-jitter`
- Routing backend: `--osrm-base-url https://router.project-osrm.org`

## Outputs
- `alps_cities.csv` — Columns include: `name, country, latitude, longitude, population, elevation, elevation_feet, elevation_source, elevation_confidence, source, distance_km_to_alps` plus optional `hospital_*`, `airport_*`, and `driving_*` columns when enabled
- `alps_cities.geojson` — GeoJSON FeatureCollection with attributes mirrored from CSV
- `alps_cities_map.html` — Standard interactive HTML map (when `--make-map` is used)
- `alps_cities_country_map.html` — Country-colored, population-sized map (when `--make-country-map` is used)

## Notes
- Licensing: GeoNames (CC BY 4.0), OSM (ODbL). Validate terms before redistribution.
- Population completeness varies, especially for OSM if `population` tag is missing.
- If `GEONAMES_USERNAME` is not provided, the tool runs in OSM-only mode (reduced completeness).
- Default countries queried are `AT, FR, IT, DE`. Switzerland (CH), Slovenia (SI), and Liechtenstein (LI) are excluded by design in post-processing.