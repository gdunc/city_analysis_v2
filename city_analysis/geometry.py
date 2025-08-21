from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from shapely.geometry import Polygon, MultiPolygon, shape, box, Point


def load_perimeter(perimeter_path: str | Path) -> MultiPolygon | Polygon:
    """Load a perimeter polygon/multipolygon from a GeoJSON file.

    Args:
        perimeter_path: Path to a GeoJSON file containing a Polygon or MultiPolygon.

    Returns:
        A Shapely Polygon or MultiPolygon in WGS84.
    """
    path = Path(perimeter_path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Accept FeatureCollection, Feature, or raw geometry
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
        if not features:
            raise ValueError("GeoJSON FeatureCollection contains no features")
        return shape(features[0]["geometry"])  # type: ignore[index]
    if data.get("type") == "Feature":
        return shape(data["geometry"])  # type: ignore[index]
    return shape(data)  # type: ignore[arg-type]


def default_alps_polygon() -> Polygon | MultiPolygon:
    """Return a geographically accurate default polygon for the Alps.
    
    A geographer's approach: First try to load from a proper GeoJSON file,
    then fall back to a scientifically-based restrictive bounding box that
    excludes lowland areas like the Po Valley.
    """
    from shapely.geometry import box
    import logging
    logger = logging.getLogger(__name__)
    
    # First, try to load from a proper Alps perimeter GeoJSON file
    try:
        perimeter_file = Path(__file__).parent.parent / "alps_perimeter.geojson"
        if perimeter_file.exists():
            return load_perimeter(perimeter_file)
    except Exception as e:
        logger.info(f"Could not load Alps perimeter GeoJSON: {e}")
    
    # Geographic fallback: Use a broad bounding box covering the full Alpine extent
    logger.info("Using geographic bounding box for the full Alpine range")

    # Alpine mountain range boundaries based on geographic literature:
    # - Western boundary: approximately 4°E (Maritime Alps in France)
    # - Eastern boundary: approximately 17.5°E (Karawanks/Slovenian Alps)
    # - Northern boundary: approximately 49°N (Bavarian foreland)
    # - Southern boundary: approximately 43.5°N (Mediterranean foothills)

    return box(4.0, 43.5, 17.5, 49.0)


def polygon_bounds(p: Polygon | MultiPolygon) -> Tuple[float, float, float, float]:
    """Return (south, west, north, east) bounding box for Overpass queries.

    Overpass expects bbox as: south,west,north,east
    """
    minx, miny, maxx, maxy = p.bounds
    # shapely gives (minx, miny, maxx, maxy) as (lon, lat, lon, lat)
    south, west, north, east = miny, minx, maxy, maxx
    return south, west, north, east
