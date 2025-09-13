from __future__ import annotations

from typing import Dict, Iterable, List, Set

from shapely.geometry import Point, Polygon, box

# Countries to exclude from results
EXCLUDED_COUNTRY_CODES: Set[str] = {"CH", "SI", "LI"}

# Rough bounding boxes for excluded countries
CH_BOX: Polygon = box(5.96, 45.80, 10.49, 47.81)  # Switzerland
SI_BOX: Polygon = box(13.37, 45.40, 16.61, 46.88)  # Slovenia
LI_BOX: Polygon = box(9.47, 47.05, 9.64, 47.27)    # Liechtenstein

EXCLUDED_BOXES: List[Polygon] = [CH_BOX, SI_BOX, LI_BOX]

# Rough bounding boxes for included countries to infer missing country codes
AT_BOX: Polygon = box(9.53, 46.37, 17.16, 49.02)
DE_BOX: Polygon = box(5.87, 47.27, 15.04, 55.06)
FR_BOX: Polygon = box(-5.14, 41.33, 9.56, 51.09)
IT_BOX: Polygon = box(6.62, 35.29, 18.79, 47.09)

# Prioritize countries with higher risk of overlap: DE before AT (Munich), IT before FR (Turin/Milan).
COUNTRY_BBOXES = [
    ("DE", DE_BOX),
    ("IT", IT_BOX),
    ("AT", AT_BOX),
    ("FR", FR_BOX),
]


def should_exclude_record(record: Dict) -> bool:
    country = str(record.get("country", "")).upper()
    if country in EXCLUDED_COUNTRY_CODES:
        return True
    # Fallback: if no country, use rough bbox to filter
    if not country:
        try:
            lat = float(record["latitude"])  # type: ignore[index]
            lon = float(record["longitude"])  # type: ignore[index]
            pt = Point(lon, lat)
            for bbox in EXCLUDED_BOXES:
                if bbox.contains(pt):
                    return True
        except Exception:
            pass
    return False


def filter_excluded_countries(records: Iterable[Dict]) -> List[Dict]:
    return [r for r in records if not should_exclude_record(r)]


def fill_missing_country(records: Iterable[Dict]) -> List[Dict]:
    filled: List[Dict] = []
    for r in records:
        country = str(r.get("country", "")).upper()
        if country:
            filled.append(r)
            continue
        try:
            lat = float(r["latitude"])  # type: ignore[index]
            lon = float(r["longitude"])  # type: ignore[index]
            pt = Point(lon, lat)
            inferred = ""
            for code, bbox in COUNTRY_BBOXES:
                if bbox.contains(pt):
                    inferred = code
                    break
            if inferred:
                r = {**r, "country": inferred}
        except Exception:
            pass
        filled.append(r)
    return filled


def infer_country_by_bbox(lat: float, lon: float) -> str:
    """Infer ISO 3166-1 alpha-2 country from rough bbox membership.

    Uses an order tuned for Central Europe; works reasonably for Alps and Pyrenees.
    """
    pt = Point(lon, lat)
    # Conflict-resolution priority for the Alps
    resolution_priority = [
        ("AT", AT_BOX),
        ("IT", IT_BOX),
        ("DE", DE_BOX),
        ("FR", FR_BOX),
    ]
    for code, bbox in resolution_priority:
        if bbox.contains(pt):
            return code
    return ""
