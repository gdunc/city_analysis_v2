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


def default_alps_polygon_with_source() -> Tuple[Polygon | MultiPolygon, str]:
    """Return a geographically accurate default polygon for the Alps and its source.

    Returns a tuple ``(polygon, source)`` where ``source`` is ``"data_source"`` if
    the dedicated GeoJSON perimeter file was successfully loaded or ``"fallback"``
    if a broad bounding box was used instead.
    """
    from shapely.geometry import box
    import logging

    logger = logging.getLogger(__name__)

    try:
        perimeter_file = Path(__file__).parent.parent / "alps_perimeter.geojson"
        if perimeter_file.exists():
            return load_perimeter(perimeter_file), "data_source"
    except Exception as e:
        logger.warning(f"Could not load Alps perimeter GeoJSON: {e}")

    logger.info("Using geographic bounding box for the full Alpine range")

    return box(4.0, 43.5, 17.5, 49.0), "fallback"


def default_alps_polygon() -> Polygon | MultiPolygon:
    """Return a geographically accurate default polygon for the Alps.

    This is a backwards-compatible wrapper around
    :func:`default_alps_polygon_with_source` that discards the source
    information.
    """
    polygon, _ = default_alps_polygon_with_source()
    return polygon


def polygon_bounds(p: Polygon | MultiPolygon) -> Tuple[float, float, float, float]:
    """Return (south, west, north, east) bounding box for Overpass queries.

    Overpass expects bbox as: south,west,north,east
    """
    minx, miny, maxx, maxy = p.bounds
    # shapely gives (minx, miny, maxx, maxy) as (lon, lat, lon, lat)
    south, west, north, east = miny, minx, maxy, maxx
    return south, west, north, east
