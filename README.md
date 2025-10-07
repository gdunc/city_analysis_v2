# City Analysis v2 — Mountain Region Cities (Population + Coordinates)

Minimal toolchain to fetch and analyze cities in and near mountain regions (Alps, Pyrenees, Rockies) from GeoNames and OSM (Overpass), clipped to regional perimeters, with CSV/GeoJSON outputs, optional elevation enrichment, hospital presence check, and interactive maps.

## Features
- **Population and coordinates** from GeoNames and OpenStreetMap
- **Elevation** from OSM/GeoNames, with optional multi-source enrichment (OpenTopoData, Google, Open‑Elevation)
- **Distance to region perimeter** computed for each place (Alps, Pyrenees, or Rockies)
- **Country filtering** with automatic country inference for missing codes
- **Population threshold** filtering
- **Interactive maps**:
  - Standard clustered map with color by population tier and a built-in client-side filter UI (min population, max driving times, hospital presence)
  - Country-colored, population-sized map with **unified peaks layer** (single checkbox for all peaks instead of per-country peak layers)
  - **Alps-centered default view** - maps now open centered over the Alpine region (46.5°N, 10°E) instead of random ocean locations
- **Hospital presence check** via OSM by default; OpenAI mode only when explicitly enabled
- **Nearest international airport + driving** offline-first using OurAirports dataset + OSRM; OpenAI web search mode can be explicitly enabled
- **CSV-to-map mode**: build maps directly from an existing CSV without refetching data
- **Nearby higher peaks**: counts and lists OSM `natural=peak` within a radius that are at least a specified elevation above the city (defaults: ≥1200 m within 30 km)
- **Multi-region analysis**: combine data from multiple regions into unified maps and analyses
- **Interactive Dash app**: web-based filtering and visualization tool for exploring city data across regions
- **Statistical analysis**: automated generation of correlation plots, scatter plots, and summary statistics
- **Optimized maps**: 99% smaller HTML files with external data files for faster loading and better caching
- **Legal compliance**: Complete attribution, terms of service, privacy policy, and license documentation
- **WordPress integration**: Ready-to-deploy maps with WordPress compatibility and hosting instructions

## Architecture (CTO-level overview)
- `city_analysis/geometry.py`: Perimeter handling (load GeoJSON, default region polygons/bbox, Overpass bbox conversion)
- `city_analysis/geonames.py`: GeoNames API client with pagination, normalized records
- `city_analysis/overpass.py`: Overpass QL builder and fetcher, normalized records (`place=city|town|village`)
- `city_analysis/normalize.py`: Perimeter filtering and deduplication by name + proximity with country resolution
- `city_analysis/distance.py`: Distance-to-perimeter computation (km) for each place
- `city_analysis/elevation.py`: Multi-source elevation enrichment (OpenTopoData → Google → Open‑Elevation)
- `city_analysis/country_filters.py`: Exclude CH/SI/LI; infer missing country by bbox for AT/DE/FR/IT
- `city_analysis/io_utils.py`: CSV and GeoJSON writers/readers
- `city_analysis/analysis.py`: Summary metrics and top-N by population
- `city_analysis/hospital_check.py`: Optional hospital presence enrichment via OSM (default) or OpenAI/hybrid
- `city_analysis/airport_check.py`: Optional nearest international airport enrichment via OpenAI web search + OSRM driving metrics
- `city_analysis/peak_check.py`: Nearby higher peaks enrichment using OSM `natural=peak` and `ele` tags
- `city_analysis/extract_rockies.py`: Rockies region perimeter extraction from GMBA dataset
- `city_analysis/cli.py`: CLI orchestration with multi-region combine functionality
- `city_analysis/map_utils.py`: Folium map builders and savers (standard and country-colored)
- `city_analysis/combine_analyze.py`: Multi-region data combination and statistical analysis
- `city_analysis/dash_app.py`: Interactive Dash web application for data exploration

## Data Sources
- **GeoNames**: Population, coordinates, country codes (requires free account)
- **OpenStreetMap (OSM)**: Population, coordinates, country codes, elevation tags (`ele`/`height`)
- **OSM peaks**: `natural=peak` points with `ele` for nearby higher peaks analysis
- **Elevation enrichment**: OpenTopoData, Google Elevation API, Open‑Elevation
- **OurAirports**: Airport metadata (large/medium; scheduled service; IATA/ICAO; coordinates) for offline nearest-airport lookup
- **OSRM**: Routing for driving distance/time
- **GMBA (Global Mountain Biodiversity Assessment)**: Mountain region boundaries for Rockies perimeter extraction

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

**New dependencies for analysis and visualization:**
- `matplotlib` and `seaborn` for statistical plotting
- `plotly` and `dash` for interactive web applications
- `dash-bootstrap-components` for enhanced UI components

## Configuration
- **GeoNames (required)**: Set `GEONAMES_USERNAME` env var or pass `--geonames-username`. The run aborts if GeoNames cannot be fetched.
- **Google Elevation API** (optional): Set `GOOGLE_API_KEY` or pass `--google-api-key`.
- **OpenAI (optional)**: Set `OPENAI_API_KEY` only if you explicitly enable OpenAI modes. Optional `--openai-model` (default `gpt-5`) and `--openai-timeout`.
- **OSRM routing** (optional for airports): Default public server is used. Override with `--osrm-base-url` if you have your own OSRM instance.
- **Region & Perimeter**: Prefer `--region` to pick a built-in region (auto-resolves perimeters under `data/regions/<region>/perimeter.geojson` when present). You can override with `--perimeter PATH`.

The CLI auto-loads a `.env` file if present (via `python-dotenv`). Example:
```bash
# .env
GEONAMES_USERNAME=your_user
GOOGLE_API_KEY=your_key   # optional
OPENAI_API_KEY=sk-...     # optional, for --check-hospitals
```
The repo includes example perimeter files:
- `alps_perimeter.geojson` - Alps region
- `data/regions/pyrenees/perimeter.geojson` - Pyrenees region  
- `data/regions/rockies/perimeter.geojson` - Rockies region

### Built-in regions
Use `--region` to select one of the built-in configurations (defaults in parentheses):

- `alps` (countries: AT, FR, IT, DE; excludes CH, SI, LI)
- `pyrenees` (FR, ES, AD)
- `rockies` (US, CA)
- `sierra_nevada` (US, MX)
- `cascade_range` (US, CA)
- `coast_mountains` (US, CA)

Region defaults can be overridden via `--region-config <file.yaml>`.

Example region YAML keys: `name, slug, countries, perimeter_geojson, excluded_countries, map_tiles, min_population, require_osm_population`.

## Usage

### Alps Analysis (default)
```bash
python -m city_analysis.cli --geonames-username YOUR_GEONAMES_USER --out-dir outputs
```
Example using the included Alps perimeter file and generating both maps:
```bash
python -m city_analysis.cli \
  --geonames-username YOUR_GEONAMES_USER \
  --region alps \
  --make-map \
  --make-country-map \
  --out-dir outputs
```

### Pyrenees Analysis
```bash
python -m city_analysis.cli \
  --geonames-username YOUR_GEONAMES_USER \
  --region pyrenees \
  --make-map \
  --make-country-map \
  --out-dir outputs
```

### Rockies Analysis
```bash
python -m city_analysis.cli \
  --geonames-username YOUR_GEONAMES_USER \
  --region rockies \
  --make-map \
  --make-country-map \
  --out-dir outputs
```

Notes:
- Outputs are written under `outputs/<region>/...` automatically. Keep `--out-dir` as a base like `outputs` to avoid double nesting.

### CLI options: what they do and when to use them
- **--region SLUG**: Select a built-in region (default `alps`).
- **--region-config FILE.yaml**: Provide a YAML to override region defaults.
- **--geonames-username USER**: GeoNames username (required).
- **--perimeter FILE.geojson**: Override region perimeter with a custom GeoJSON.
- **--countries CODES...**: Restrict to specific countries; defaults to the region settings.
- **--min-population N**: Minimum population filter for GeoNames and final output.
- **--tile-size DEG**: Overpass tiling size in degrees.
- **--out-dir PATH**: Base output directory (actual outputs go under `<out-dir>/<region>`).
- **--top N**: How many top-by-population entries to print to the console.

- **--google-api-key KEY**: Enables Google Elevation fallback (paid).
- **--elevation-batch-size N**: Batch size for elevation requests.
- **--skip-elevation**: Skip elevation enrichment.

- **--make-map**: Generate the standard clustered map.
- **--map-file PATH**: Custom path for the standard map HTML.
- **--map-tiles NAME|URL**: Folium tiles name/URL (overrides region default).
- **--make-country-map**: Generate the country-colored, population-sized map.
- **--country-map-file PATH**: Custom path for the country map HTML.

- **--from-csv FILE.csv**: Build maps and/or run optional enrichments from an existing CSV.

- Peaks enrichment (optional):
  - **--check-peaks**: Add columns for nearby higher peaks.
  - **--peaks-radius-km KM**: Search radius around city centroid (default 30.0).
  - **--peaks-min-height-diff-m M**: Only count peaks at least this much higher than the city elevation (default 1200.0).
  - **--peaks-tile-size DEG**: Overpass tile size for peaks fetch (default 1.0).

- Advanced/CSV-only enrichments:
  - **--check-hospitals**: Add hospital presence columns (OSM by default; OpenAI if enabled).
  - **--hospital-mode [osm|openai|hybrid]** and related tuning flags.
  - **--check-airports**: Add nearest airport + driving columns (offline by default; OpenAI mode opt-in).
  - **--airports-***: Dataset, radius/top‑K, retries/backoff, limits, resume.
  - **--osrm-base-url URL**: Routing backend for driving metrics.

- Pipeline controls:
  - **--stage [fetch|filter|dedupe|enrich_elevation|enrich_hospitals|enrich_peaks|enrich_airports|maps|all]**
  - **--resume**: Reuse cached tiles/intermediate files when available

- Multi-region combination:
  - **--combine-regions SLUGS...**: Combine specific regions into unified maps
  - **--combine-all**: Automatically combine all available regions
  - **--combined-slug SLUG**: Custom slug for combined output folder (default: "all_regions")
  - **--combined-name NAME**: Display name for combined output (default: "All Regions")

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
- Standard map: `outputs/alps/alps_cities_map.html`
- Country map: `outputs/alps/alps_cities_country_map.html`

### Map details
- **Default view:** Maps now open centered over the Alpine region (46.5°N, 10°E) for better initial user experience
- **Marker colors (standard map):**
  - darkred: ≥ 100,000
  - red: 50,000–99,999
  - orange: 20,000–49,999
  - green: 10,000–19,999
  - blue: < 10,000 or missing
- **Popup content (standard and country maps):**
  - City name, country, population
  - Elevation formatted as `Elevation: XXX m / X,XXX ft` (with source tag)
  - Nearest airport name (when available)
  - Note: Distance to region remains in CSV but is not shown in the popup
- **Filters (top-left):**
  - Min population
  - Max driving time to airport (minutes)
  - Max driving time to hospital (minutes)
  - Hospital in city? any/yes/no
  - Hospital in city or nearby? any/yes/no
  - Applied client-side without reloading
- **Layer controls (top-right):**
  - **Standard map:** Cities layer + unified "Peaks (≥1200m over city within 30km)" layer
  - **Country map:** Individual country layers + unified peaks layer (single checkbox for all peaks)
- **Country map:** Markers are colored by country and sized by log-scaled population; each country is toggleable in the layer control.

### Build maps directly from an existing CSV
```bash
python -m city_analysis.cli --from-csv outputs/alps_cities.csv --make-map --make-country-map --out-dir outputs
```
If `--make-map`/`--make-country-map` are omitted with `--from-csv`, both maps are generated by default.

Optionally enrich from CSV with nearby higher peaks (defaults shown):
```bash
python -m city_analysis.cli \
  --from-csv outputs/alps_cities.csv \
  --check-peaks \
  --peaks-radius-km 30 \
  --peaks-min-height-diff-m 1200 \
  --out-dir outputs
```

### Multi-region analysis and visualization

#### Combine multiple regions into unified maps
Combine specific regions into a single map:
```bash
python -m city_analysis.cli --combine-regions alps pyrenees rockies --out-dir outputs
```

Combine all available regions automatically:
```bash
python -m city_analysis.cli --combine-all --out-dir outputs
```

Customize the combined output:
```bash
python -m city_analysis.cli \
  --combine-regions alps pyrenees \
  --combined-slug alps_pyrenees \
  --combined-name "Alps & Pyrenees" \
  --out-dir outputs
```

#### Statistical analysis and plotting
Generate comprehensive analysis plots from combined regional data:
```bash
python -m city_analysis.combine_analyze --outputs-dir outputs --out-dir outputs/combined
```

This creates:
- **Static plots**: Scatter plots for hospital vs airport time, peaks vs airport time, population vs peaks
- **Interactive plots**: HTML versions with hover details and zoom capabilities  
- **Summary statistics**: CSV with regional breakdowns and correlation analysis
- **Combined dataset**: Single CSV with all regional data

#### Interactive Dash web application
Launch an interactive web app for exploring city data across regions:
```bash
python -m city_analysis.dash_app --outputs-dir outputs --out-dir outputs/combined
```

Access at `http://127.0.0.1:8050` with features:
- **Multi-dimensional filtering**: Region, country, population, elevation, driving times, peaks count
- **Real-time plots**: Three synchronized scatter plots update based on filters
- **Hover details**: City names, countries, and key metrics on hover
- **Responsive design**: Sidebar filters with main plotting area

Customize the web app:
```bash
python -m city_analysis.dash_app \
  --outputs-dir outputs \
  --out-dir outputs/combined \
  --host 0.0.0.0 \
  --port 8080 \
  --debug
```

### Generate optimized maps for public deployment
Create web-ready maps with legal compliance and optimized file sizes:
```bash
python generate_optimized_maps.py --outputs-dir outputs --out-dir outputs/combined
```

This generates:
- **Optimized HTML files**: 99% smaller than standard maps (23KB vs 30-50MB)
- **External data files**: Separate JSON files for better caching
- **Legal documentation**: Complete attribution, terms, privacy policy
- **WordPress integration**: Ready-to-deploy with hosting instructions

**Deployment options:**
- **Static hosting**: Upload to Netlify, Vercel, GitHub Pages, S3 + CloudFront
- **WordPress**: Upload HTML and JSON files to Media Library
- **Local testing**: `python3 -m http.server 8000` in the output directory

**Legal compliance features:**
- ✅ Complete data source attribution
- ✅ Terms of Service and Privacy Policy
- ✅ GDPR/CCPA compliant (no tracking, no cookies)
- ✅ Commercial use permitted with attribution
- ✅ All third-party licenses documented

### Hospital presence check
Full pipeline (`--stage all`) always enriches hospital presence via OSM by default. In CSV-only mode (`--from-csv`), you can opt in with `--check-hospitals`. The enrichment writes:

- `hospital_in_city` ("yes"|"no")
- `hospital_confidence_pct` (0–100)
- `hospital_reasoning` (brief rationale + up to 3 links)
- `hospital_error` (error message if any)

In OSM and hybrid modes, additional convenience fields are included:

- `hospital_nearest_name`, `hospital_nearest_latitude`, `hospital_nearest_longitude`
- `nearest_hospital_km`, `hospital_in_city_or_nearby` ("yes" within 25 km)
- `driving_km_to_hospital`, `driving_time_minutes_to_hospital`

Usage (CSV-only, default OSM mode):
```bash
python -m city_analysis.cli --check-hospitals --out-dir outputs
```

Control the radius and tiling:
```bash
python -m city_analysis.cli --check-hospitals --hospital-radius-km 4 --hospital-tile-size 0.5 --out-dir outputs
```

Explicitly use OpenAI mode (CSV-only, opt-in):
```bash
OPENAI_API_KEY=sk-... python -m city_analysis.cli --check-hospitals --hospital-mode openai --out-dir outputs
```

Hybrid mode (CSV-only; OSM first, then OpenAI only when OSM finds none):
```bash
OPENAI_API_KEY=sk-... python -m city_analysis.cli --check-hospitals --hospital-mode hybrid --out-dir outputs
```

### Nearest international airport + driving
Full pipeline (`--stage all`) always enriches airports via the offline dataset by default. In CSV-only mode (`--from-csv`), you can opt in with `--check-airports`. Adds columns for nearest airport and driving metrics. Offline by default; OpenAI web search mode is available if explicitly enabled.
- `airport_nearest_name`, `airport_nearest_iata`, `airport_nearest_icao`
- `airport_nearest_latitude`, `airport_nearest_longitude`
- `airport_confidence_pct` (0–100), `airport_reasoning` (brief rationale + links), `airport_error`
- `driving_km_to_airport`, `driving_time_minutes_to_airport`
- `driving_confidence_pct`, `driving_reasoning`, `driving_error`

Offline default (CSV-only from any existing CSV):
```bash
python -m city_analysis.cli \
  --from-csv outputs/alps_cities.csv \
  --check-airports \
  --out-dir outputs
```

Opt-in OpenAI mode:
```bash
OPENAI_API_KEY=sk-... python -m city_analysis.cli \
  --from-csv outputs/alps_cities.csv \
  --check-airports \
  --airports-use-openai \
  --out-dir outputs \
  --openai-model gpt-5 \
  --openai-timeout 90
```

Controls:
- Offline mode: dataset path `--airports-dataset PATH` (auto-downloads if omitted to `ignore/airports_ourairports.csv`), top‑K `--airports-topk`, radius `--airports-max-radius-km`, routing backend `--osrm-base-url`.
- OpenAI mode: reliability/backoff `--airports-max-retries`, `--airports-initial-backoff`, `--airports-backoff-multiplier`, `--airports-jitter`.
- General: limits and resume `--airports-limit`, `--airports-resume-missing`.

### Nearby higher peaks
Compute, for each city, OSM `natural=peak` within a given radius that are at least a minimum elevation difference above the city (defaults: ≥1200 m within 30 km). Adds convenient count and names, plus a structured list (also mirrored in the companion details JSON).

Usage in full pipeline (peaks are part of `--stage all`):
```bash
python -m city_analysis.cli \
  --geonames-username YOUR_GEONAMES_USER \
  --region alps \
  --make-map --make-country-map \
  --out-dir outputs
```

Run only the peaks stage against a previously enriched elevation/hospital step:
```bash
python -m city_analysis.cli --stage enrich_peaks --out-dir outputs
```

CSV-only mode (no refetch): see example above under “Build maps directly from an existing CSV”.

## Outputs

### Per-region outputs
- `{region}_cities.csv` — Columns include: `name, country, latitude, longitude, population, elevation, elevation_feet, elevation_source, elevation_confidence, source, distance_km_to_region`.
  - If hospital presence is enabled: `hospital_in_city, hospital_confidence_pct, hospital_reasoning, hospital_error, hospital_nearest_name, hospital_nearest_latitude, hospital_nearest_longitude, nearest_hospital_km, hospital_in_city_or_nearby, driving_km_to_hospital, driving_time_minutes_to_hospital`
  - If nearest airport is enabled: `airport_nearest_name, airport_nearest_iata, airport_nearest_icao, airport_nearest_latitude, airport_nearest_longitude, airport_confidence_pct, airport_reasoning, airport_error, driving_km_to_airport, driving_time_minutes_to_airport, driving_confidence_pct, driving_reasoning, driving_error`
  - If nearby higher peaks is enabled (defaults shown): `peaks_higher1200_within30km_count, peaks_higher1200_within30km_names`. A structured list `peaks_higher1200_within30km` is included in the details JSON.
- `{region}_cities.geojson` — GeoJSON FeatureCollection with attributes mirrored from CSV
- `{region}_cities_map.html` — Standard interactive HTML map (when `--make-map` is used)
- `{region}_cities_country_map.html` — Country-colored, population-sized map (when `--make-country-map` is used)

Where `{region}` is `alps`, `pyrenees`, or `rockies` depending on the analysis.

### Multi-region analysis outputs
When using `--combine-regions` or `--combine-all`:
- `{combined_slug}_cities.csv` — Combined dataset with all regions and `region` column for identification
- `{combined_slug}_cities.geojson` — Combined GeoJSON with all regional data
- `{combined_slug}_cities_map.html` — Unified interactive map showing all regions
- `{combined_slug}_cities_country_map.html` — Unified country-colored map

When running `city_analysis.combine_analyze`:
- `all_regions_cities.csv` — Combined dataset from all available regions
- **Static plots** (PNG format):
  - `scatter_hospital_time_vs_airport_time.png` — Hospital vs airport driving time correlation
  - `scatter_peaks_count_vs_airport_time.png` — Peaks count vs airport accessibility
  - `scatter_population_vs_peaks_count.png` — Population vs nearby peaks relationship
  - `correlation_heatmap.png` — Full correlation matrix of numeric variables
- **Interactive plots** (HTML format):
  - `scatter_hospital_time_vs_airport_time.html` — Interactive version with hover details
  - `scatter_peaks_count_vs_airport_time.html` — Interactive version with hover details
  - `scatter_population_vs_peaks_count.html` — Interactive version with hover details
- `summary_by_region.csv` — Statistical summary by region (count, mean, median, min, max)

### Optimized maps for public deployment
When running `generate_optimized_maps.py`:
- `all_regions_cities_map_optimized.html` — Standard map optimized for web hosting (~23 KB)
- `all_regions_cities_country_map_optimized.html` — Country map optimized for web hosting (~25 KB)
- `all_regions_cities_map_optimized.data.json` — Shared data file (~3.5 MB)
- `all_regions_cities_country_map_optimized.data.json` — Shared data file (~3.5 MB)
- `attribution.html` — Complete attribution and data source licenses
- `terms.html` — Terms of Service
- `privacy.html` — Privacy Policy (GDPR/CCPA compliant)
- `wordpress_example.html` — WordPress integration guide
- `LICENSES.md` — Full text of all third-party licenses

**Benefits of optimized maps:**
- 99% smaller HTML files (23KB vs 30-50MB)
- Faster initial page load
- Better browser caching (HTML and data cached separately)
- Legal compliance for public use
- WordPress-ready deployment

## Notes
- Licensing: GeoNames (CC BY 4.0), OSM (ODbL). Validate terms before redistribution.
- Population completeness varies, especially for OSM if `population` tag is missing.
- `GEONAMES_USERNAME` is required; the tool aborts if GeoNames fetch fails.
- Default countries queried are `AT, FR, IT, DE` for Alps. Switzerland (CH), Slovenia (SI), and Liechtenstein (LI) are excluded by design in post-processing for Alps analysis.
- For Pyrenees: use `ES, FR, AD` (Spain, France, Andorra)
- For Rockies: use `US, CA` (United States, Canada)