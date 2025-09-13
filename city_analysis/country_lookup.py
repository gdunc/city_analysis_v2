from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import requests
from shapely.geometry import Point, shape
from shapely.strtree import STRtree


class CountryBoundaryIndex:
    """Lightweight ISO A2 country lookup using Natural Earth Admin 0 geojson.

    - Downloads and caches the GeoJSON on first use under data/cache/.
    - Builds an STRtree for fast point-in-polygon lookups.
    - Exposes lookup by (lat, lon) with optional allowed country filter.
    """

    _CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
    _CACHE_FILE = _CACHE_DIR / "ne_50m_admin_0_countries.geojson"
    _DOWNLOAD_URLS = [
        # Primary: Natural Earth official mirror (GitHub)
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson",
        # Fallback: 110m if 50m fails (less precise but fine for country boundaries)
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson",
    ]

    _instance: Optional["CountryBoundaryIndex"] = None

    def __init__(self, features: List[Dict]):
        self._geoms: List = []
        self._codes: List[str] = []
        self._geom_wkb_to_code: Dict[bytes, str] = {}
        for feat in features:
            props = feat.get("properties", {})
            # Try multiple property names that may contain ISO A2
            code = (
                props.get("ISO_A2")
                or props.get("ISO_A2_EH")
                or props.get("ADM0_A3_IS")
                or props.get("ADM0_A3")
                or props.get("WB_A2")
                or ""
            )
            code = str(code).upper()
            # Normalize common exceptions
            if code == "UK":
                code = "GB"
            # Skip invalid/placeholder codes like -99
            if not code or code == "-99":
                continue
            try:
                geom = shape(feat.get("geometry"))
            except Exception:
                continue
            self._geoms.append(geom)
            self._codes.append(code)
            try:
                self._geom_wkb_to_code[geom.wkb] = code
            except Exception:
                pass

        # Build spatial index
        self._tree = STRtree(self._geoms)
        # Keep parallel lists for index-based fallback
        self._index_to_code: List[str] = list(self._codes)

    @classmethod
    def instance(cls) -> "CountryBoundaryIndex":
        if cls._instance is None:
            features = cls._load_or_download()
            cls._instance = CountryBoundaryIndex(features)
        return cls._instance

    @classmethod
    def _load_or_download(cls) -> List[Dict]:
        cls._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if cls._CACHE_FILE.exists():
            try:
                data = json.loads(cls._CACHE_FILE.read_text(encoding="utf-8"))
                feats = data.get("features") or []
                return feats  # type: ignore[return-value]
            except Exception:
                pass
        # Try downloads in order
        for url in cls._DOWNLOAD_URLS:
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                resp.encoding = "utf-8"
                data = resp.json()
                feats = data.get("features") or []
                # Cache
                try:
                    cls._CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
                except Exception:
                    pass
                return feats  # type: ignore[return-value]
            except Exception:
                continue
        # Last resort: empty list
        return []

    def lookup_iso_a2(self, lat: float, lon: float, allowed: Optional[Iterable[str]] = None) -> str:
        pt = Point(lon, lat)
        raw_candidates = self._tree.query(pt)
        try:
            candidates_list = list(raw_candidates)
        except Exception:
            candidates_list = [raw_candidates]
        if len(candidates_list) == 0:
            return ""
        allowed_set: Optional[Set[str]] = set(x.upper() for x in allowed) if allowed else None

        # Normalize candidates to (geom, code)
        norm: List[Tuple[object, str]] = []
        for c in candidates_list:
            # Shapely 2 often returns integer indices; convert to geom+code
            idx = None
            try:
                idx = int(c)
            except Exception:
                idx = None
            if idx is not None and 0 <= idx < len(self._geoms):
                geom = self._geoms[idx]
                code = self._codes[idx]
                norm.append((geom, code))
            else:
                geom = c
                try:
                    code = self._geom_wkb_to_code.get(geom.wkb, "")  # type: ignore[attr-defined]
                except Exception:
                    code = ""
                norm.append((geom, code))

        # Prefer true containment
        for geom, code in norm:
            try:
                if getattr(geom, "contains", lambda *_: False)(pt):
                    if code and (allowed_set is None or code in allowed_set):
                        return code
            except Exception:
                continue

        # Next, allow boundary touches
        for geom, code in norm:
            try:
                if getattr(geom, "touches", lambda *_: False)(pt):
                    if code and (allowed_set is None or code in allowed_set):
                        return code
            except Exception:
                continue

        # If none matched predicate, choose nearest among allowed
        best_code = ""
        best_dist = float("inf")
        for geom, code in norm:
            try:
                if not code:
                    continue
                if allowed_set is not None and code not in allowed_set:
                    continue
                d = getattr(geom, "distance", lambda *_: float("inf"))(pt)
                if d < best_dist:
                    best_dist = d
                    best_code = code
            except Exception:
                continue
        if best_code:
            return best_code

        # Fallback: return any candidate's code
        for _, code in norm:
            if code:
                return code
        return ""


def infer_country_iso_a2(lat: float, lon: float, allowed: Optional[Iterable[str]] = None) -> str:
    return CountryBoundaryIndex.instance().lookup_iso_a2(lat, lon, allowed=allowed)


