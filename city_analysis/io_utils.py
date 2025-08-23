from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List

import folium


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
    
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        # Ensure proper UTF-8 handling for special characters
        for record in records_list:
            # Clean any potential encoding issues in the data
            cleaned_record = {}
            for key, value in record.items():
                if isinstance(value, str):
                    # Ensure the string is properly encoded
                    try:
                        cleaned_record[key] = value.encode('utf-8').decode('utf-8')
                    except UnicodeError:
                        # Fallback: try to fix common encoding issues
                        cleaned_record[key] = value.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore')
                else:
                    cleaned_record[key] = value
            writer.writerow(cleaned_record)


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


def write_html_map(path: str | Path, records: Iterable[Dict]) -> None:
    """Write an interactive HTML map using Folium for the given places."""
    records_list: List[Dict] = list(records)
    if not records_list:
        Path(path).write_text("")
        return

    # Center map around average coordinates
    center_lat = sum(float(r["latitude"]) for r in records_list) / len(records_list)
    center_lon = sum(float(r["longitude"]) for r in records_list) / len(records_list)
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=6)

    for r in records_list:
        popup = f"{r.get('name', 'Unknown')} ({r.get('country', '')})"
        if r.get("population"):
            try:
                popup += f" — pop {int(r['population']):,}"
            except Exception:
                popup += f" — pop {r['population']}"
        folium.Marker([
            float(r["latitude"]),
            float(r["longitude"]),
        ], popup=popup).add_to(fmap)

    fmap.save(str(path))


def write_html_map_by_country_and_population(path: str | Path, records: Iterable[Dict]) -> None:
    """Write a Folium map with circle markers colored by country and sized by population."""
    records_list: List[Dict] = list(records)
    if not records_list:
        Path(path).write_text("")
        return

    center_lat = sum(float(r["latitude"]) for r in records_list) / len(records_list)
    center_lon = sum(float(r["longitude"]) for r in records_list) / len(records_list)
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=6)

    populations = [int(r.get("population") or 0) for r in records_list if r.get("population")]
    min_pop = min(populations) if populations else 0
    max_pop = max(populations) if populations else 0

    # Assign a color for each country
    country_codes = sorted({r.get("country", "") for r in records_list})
    color_palette = [
        "red", "blue", "green", "purple", "orange", "darkred", "lightred",
        "beige", "darkblue", "darkgreen", "cadetblue", "darkpurple",
        "white", "pink", "lightblue", "lightgreen", "gray", "black", "lightgray",
    ]
    country_colors = {c: color_palette[i % len(color_palette)] for i, c in enumerate(country_codes)}

    def scale_radius(pop: int) -> float:
        if max_pop == min_pop:
            return 5
        # Scale radius between 5 and 20 pixels
        return 5 + (pop - min_pop) / (max_pop - min_pop) * 15

    for r in records_list:
        pop = int(r.get("population") or 0)
        country = r.get("country", "")
        popup = f"{r.get('name', 'Unknown')} ({country})"
        if pop:
            try:
                popup += f" — pop {pop:,}"
            except Exception:
                popup += f" — pop {r['population']}"
        folium.CircleMarker(
            location=[float(r["latitude"]), float(r["longitude"])],
            radius=scale_radius(pop),
            color=country_colors.get(country, "gray"),
            fill=True,
            fill_opacity=0.7,
            fill_color=country_colors.get(country, "gray"),
            popup=popup,
        ).add_to(fmap)

    fmap.save(str(path))
