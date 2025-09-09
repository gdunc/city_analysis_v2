from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List


def write_csv(path: str | Path, records: Iterable[Dict]) -> None:
    records_list: List[Dict] = list(records)
    if not records_list:
        Path(path).write_text("")
        return
    
    # Collect all possible fieldnames from all records
    all_fieldnames = set()
    for record in records_list:
        all_fieldnames.update(record.keys())
    
    # Use a consistent field order for better readability
    field_order = [
        "name", "country", "latitude", "longitude", "population", 
        "elevation", "elevation_feet", "elevation_source", "elevation_confidence",
        "source", "distance_km_to_alps"
    ]
    
    # Start with ordered fields, then add any remaining fields
    fieldnames = [f for f in field_order if f in all_fieldnames]
    remaining_fields = sorted([f for f in all_fieldnames if f not in field_order])
    fieldnames.extend(remaining_fields)
    
    # Write CSV with UTF-8 BOM so spreadsheet apps (e.g., Excel) detect encoding correctly
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records_list:
            writer.writerow(record)


def write_geojson(path: str | Path, records: Iterable[Dict]) -> None:
    features: List[Dict] = []
    for r in records:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])],
                },
                "properties": {k: v for k, v in r.items() if k not in {"longitude", "latitude"}},
            }
        )
    fc = {"type": "FeatureCollection", "features": features}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
