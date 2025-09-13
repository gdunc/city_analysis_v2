## Pyrenees perimeter data

- **Files:**
  - `perimeter.geojson`
  - `perimeter_buffer_10km.geojson`

### Provenance
- **Source:** Derived from the GMBA Mountain Inventory v2.0 (standard). Global Mountain Biodiversity Assessment (GMBA).
- **Selection:** GMBA polygons corresponding to the Pyrenees across France (FR), Spain (ES), and Andorra (AD).
- **Notes in data:**
  - `perimeter.geojson` properties include: `source = "GMBA v2 (hierarchy+FR/ES/AD), tol=150m"`
  - `perimeter_buffer_10km.geojson` properties include: `source = "GMBA v2 (hierarchy+FR/ES/AD), tol=150m, buffer=10km"`

### Processing summary
- Simplified geometry with ~150 m tolerance (Douglas–Peucker style) to reduce vertex count while preserving shape.
- Produced a second file buffered outward by 10 km for analyses that benefit from a padded study area (e.g., context queries near the boundary).

### Coordinate reference system
- Coordinates are longitude/latitude in WGS84 (GeoJSON default). Files also declare `CRS84`.

### How this is used in the code
- The loader resolves a region perimeter from `data/regions/<slug>/perimeter.geojson` when present. For the Pyrenees slug (`pyrenees`), that path is: `data/regions/pyrenees/perimeter.geojson`.

### Citation
- Please cite the GMBA Mountain Inventory v2.0 when using these boundaries. See the GMBA inventory information at `https://www.gmba.unibe.ch/`.

### Changelog
- 2025-09-13: Added Pyrenees perimeter and 10 km buffer derived from GMBA v2.0.

## Pyrenees perimeter data

- **Files:**
  - `perimeter.geojson`
  - `perimeter_buffer_10km.geojson`

### Provenance
- **Source:** Derived from the GMBA Mountain Inventory v2.0 (standard). Global Mountain Biodiversity Assessment (GMBA).
- **Selection:** GMBA polygons corresponding to the Pyrenees across France (FR), Spain (ES), and Andorra (AD).
- **Notes in data:**
  - `perimeter.geojson` properties include: `source = "GMBA v2 (hierarchy+FR/ES/AD), tol=150m"`
  - `perimeter_buffer_10km.geojson` properties include: `source = "GMBA v2 (hierarchy+FR/ES/AD), tol=150m, buffer=10km"`

### Processing summary
- Simplified geometry with ~150 m tolerance (Douglas–Peucker style) to reduce vertex count while preserving shape.
- Produced a second file buffered outward by 10 km for analyses that benefit from a padded study area (e.g., context queries near the boundary).

### Coordinate reference system
- Coordinates are longitude/latitude in WGS84 (GeoJSON default). Files also declare `CRS84`.

### How this is used in the code
- The loader resolves a region perimeter from `data/regions/<slug>/perimeter.geojson` when present. For the Pyrenees slug (`pyrenees`), that path is: `data/regions/pyrenees/perimeter.geojson`.

### Citation
- Please cite the GMBA Mountain Inventory v2.0 when using these boundaries. See the GMBA inventory information at [GMBA Mountain Inventory](https://www.gmba.unibe.ch/).

### Changelog
- 2025-09-13: Added Pyrenees perimeter and 10 km buffer derived from GMBA v2.0.


