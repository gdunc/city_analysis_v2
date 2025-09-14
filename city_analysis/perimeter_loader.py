from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import requests
from shapely.geometry import Polygon, MultiPolygon, box, shape

from .config import RegionSettings
from .geometry import load_perimeter


def _project_root() -> Path:
    return Path(__file__).parent.parent


def _conventional_region_perimeter_path(slug: str) -> Path:
    return _project_root() / "data" / "regions" / slug / "perimeter.geojson"


def _write_geojson_geometry(path: Path, geom) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": json.loads(json.dumps(geom.__geo_interface__)), "properties": {}}
        ],
    }
    path.write_text(json.dumps(fc), encoding="utf-8")
    return path


def _fallback_bbox_for_slug(slug: str) -> Optional[Polygon]:
    s = slug.lower().strip()
    if s == "alps":
        return box(6.0, 45.5, 16.0, 48.0)
    if s == "pyrenees":
        # Approximate Pyrenees envelope (Bay of Biscay to Mediterranean)
        # This is a conservative mask; GMBA polygon is preferred when available.
        return box(-2.8, 42.0, 3.6, 43.8)
    if s == "rockies":
        # Approximate Rockies envelope from NM to British Columbia/Alberta
        # Conservative west/east bounds to avoid coastal and great plains spillover
        return box(-125.0, 31.0, -103.0, 60.0)
    return None


def _env_url_candidates(slug: str) -> list[str]:
    # Allow user to provide direct perimeter URL via env vars
    return [
        os.getenv(f"{slug.upper()}_PERIMETER_URL", ""),
        os.getenv("REGION_PERIMETER_URL", ""),
        os.getenv("GMBA_PERIMETER_URL", ""),
        os.getenv("GMBA_PYRENEES_URL", "") if slug.lower() == "pyrenees" else "",
    ]


def _try_download_perimeter(url: str) -> Optional[MultiPolygon | Polygon]:
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("type") in ("FeatureCollection", "Feature"):
            return load_perimeter_from_obj(data)
        return shape(data)
    except Exception:
        return None


def load_perimeter_from_obj(obj) -> MultiPolygon | Polygon:
    # Minimal mirror of geometry.load_perimeter for in-memory data
    if obj.get("type") == "FeatureCollection":
        feats = obj.get("features") or []
        if not feats:
            raise ValueError("Empty FeatureCollection")
        return shape(feats[0]["geometry"])  # type: ignore[index]
    if obj.get("type") == "Feature":
        return shape(obj["geometry"])  # type: ignore[index]
    return shape(obj)


def resolve_region_perimeter(settings: RegionSettings) -> MultiPolygon | Polygon:
    """Return a shapely perimeter for the given region, ensuring a usable geometry.

    Resolution order:
      1) settings.perimeter_geojson if provided and exists
      2) conventional path data/regions/<slug>/perimeter.geojson
      3) project-root <slug>_perimeter.geojson (legacy for Alps)
      4) download from env-provided URL(s) and cache to conventional path
      5) fallback approximate bbox by slug
    """
    # 1) Explicit path on settings
    if settings.perimeter_geojson and Path(settings.perimeter_geojson).exists():
        return load_perimeter(Path(settings.perimeter_geojson))

    # 2) Conventional path under data/regions/<slug>/
    conventional = _conventional_region_perimeter_path(settings.slug)
    if conventional.exists():
        return load_perimeter(conventional)

    # 3) Legacy project-root file
    legacy = _project_root() / f"{settings.slug}_perimeter.geojson"
    if legacy.exists():
        return load_perimeter(legacy)

    # 4) Try download via env var URLs and cache
    for url in _env_url_candidates(settings.slug):
        geom = _try_download_perimeter(url)
        if geom is not None:
            try:
                _write_geojson_geometry(conventional, geom)
            except Exception:
                pass
            return geom

    # 5) Fallback to conservative bbox
    bbox = _fallback_bbox_for_slug(settings.slug)
    if bbox is not None:
        try:
            _write_geojson_geometry(conventional, bbox)
        except Exception:
            pass
        return bbox

    # Absolute last resort: tiny global bbox that yields nothing meaningful
    return box(0.0, 0.0, 0.1, 0.1)


