# Mountain Cities Analysis - Combined Outputs

This directory contains combined interactive maps and data products produced by the original pipeline. WordPress and "optimized" variants were removed to keep full peaks detail in the maps.

## Maps (originals)
- `all_regions_cities_map.html` — Standard interactive map (full peaks layer)
- `all_regions_cities_country_map.html` — Country-colored, population-sized map (full peaks layer)

## Data files
- `all_regions_cities.csv`
- `all_regions_cities.geojson`
- Plots and summaries (PNG/HTML/CSV)

## Local testing
```bash
cd "/Users/grantduncan/Documents/coding/city_analysis_v2/outputs/combined"
python3 -m http.server 8000
```
Then open:
- http://localhost:8000/all_regions_cities_map.html
- http://localhost:8000/all_regions_cities_country_map.html

## Notes
- Maps include full peaks layer and client-side filters.
- Attribution footer is included within the map tiles layer attribution.
- For public hosting, upload the two HTML maps plus any supporting static files (plots, CSV/GeoJSON) as needed.

