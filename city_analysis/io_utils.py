from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List
import os


def write_csv(path: str | Path, records: Iterable[Dict], *, delimiter: str | None = None) -> None:
    records_list: List[Dict] = list(records)
    if not records_list:
        Path(path).write_text("")
        return
    
    # Known complex keys we do not want in CSV
    complex_keys = {
        "peaks_higher1200_within30km",
    }

    # Collect all possible scalar fieldnames from all records (exclude dict/list fields and known complex keys)
    all_fieldnames = set()
    for record in records_list:
        for k, v in record.items():
            if k in complex_keys or isinstance(v, (dict, list)):
                continue
            all_fieldnames.add(k)
    
    # Use a consistent field order for better readability
    field_order = [
        "name", "country", "latitude", "longitude", "population", 
        "elevation", "elevation_feet", "elevation_source", "elevation_confidence",
        "source", "distance_km_to_perimeter"
    ]
    
    # Start with ordered fields, then add any remaining fields
    fieldnames = [f for f in field_order if f in all_fieldnames]
    remaining_fields = sorted([f for f in all_fieldnames if f not in field_order])
    fieldnames.extend(remaining_fields)
    
    # Always default to comma; allow explicit override via parameter only
    csv_delimiter = delimiter if delimiter is not None else ","
    
    # Write CSV with UTF-8 BOM so spreadsheet apps (e.g., Excel) detect encoding correctly
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=csv_delimiter)
        writer.writeheader()
        for record in records_list:
            # Only include scalar fields; drop complex structures (saved separately)
            safe_row: Dict = {k: v for k, v in record.items() if k in fieldnames and not isinstance(v, (dict, list))}
            writer.writerow(safe_row)


def write_geojson(path: str | Path, records: Iterable[Dict]) -> None:
    features: List[Dict] = []
    for r in records:
        try:
            lat = float(r.get("latitude"))
            lon = float(r.get("longitude"))
        except Exception:
            continue
        props = dict(r)
        props.pop("latitude", None)
        props.pop("longitude", None)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")


def write_details_json(path: str | Path, records: Iterable[Dict]) -> None:
    """Write a companion JSON file with complex per-record details excluded from CSV.

    Structure:
      [
        {
          "key": "<name>|<lat>|<lon>",
          "name": "...",
          "country": "...",
          "latitude": <float>,
          "longitude": <float>,
          "details": {  # only dict/list fields from the record
             "peaks_higher1200_within30km": [...],
             ...
          }
        },
        ...
      ]
    """
    out: List[Dict] = []
    for r in records:
        try:
            lat = float(r.get("latitude"))
            lon = float(r.get("longitude"))
        except Exception:
            continue
        name = str(r.get("name") or "").strip()
        details: Dict = {}
        for k, v in r.items():
            if isinstance(v, (dict, list)):
                details[k] = v
            elif isinstance(v, str) and (v.strip().startswith("[") or v.strip().startswith("{")):
                # Try to parse JSON-like strings (e.g., peaks lists loaded from a CSV)
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, (dict, list)):
                        details[k] = parsed
                except Exception:
                    pass
        if not details:
            continue
        out.append({
            "key": f"{name}|{lat}|{lon}",
            "name": name,
            "country": r.get("country"),
            "latitude": lat,
            "longitude": lon,
            "details": details,
        })
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


def read_csv_records(path: str | Path) -> List[Dict]:
    """Read records from a UTF-8 CSV file with headers and return a list of dicts.
    Leaves value types as strings; downstream code can cast as needed.
    """
    records: List[Dict] = []
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        # Auto-detect delimiter for robustness (supports "," and ";")
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except Exception:
            class _D: delimiter = ','
            dialect = _D()
        reader = csv.DictReader(f, delimiter=dialect.delimiter)
        for row in reader:
            records.append(dict(row))
    return records


def read_details_json(path: str | Path) -> List[Dict]:
    """Read details JSON created by write_details_json.

    Returns a list of objects with keys: key, name, country, latitude, longitude, details.
    If the file does not exist or is unreadable, returns an empty list.
    """
    p = Path(path)
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, list):
            out: List[Dict] = []
            for item in data:
                if isinstance(item, dict):
                    out.append(item)
            return out
        return []
    except Exception:
        return []
