from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import List, Optional

import pandas as pd
import numpy as np


def find_region_slug(csv_path: Path) -> str:
    """Infer region slug from path parts by selecting the directory directly under 'outputs'.

    Example: outputs/pyrenees/pyrenees_cities.csv -> 'pyrenees'
             outputs/sierra_nevada/sierra_nevada_cities.csv -> 'sierra_nevada'
             outputs/sierra_nevada/sierra_nevada/sierra_nevada_cities.csv -> 'sierra_nevada'
    """
    parts = list(csv_path.parts)
    try:
        outputs_idx = parts.index("outputs")
    except ValueError:
        # Fallback: use parent directory name
        return csv_path.parent.name
    if outputs_idx + 1 < len(parts):
        return parts[outputs_idx + 1]
    return csv_path.parent.name


def load_and_standardize_csv(csv_path: Path, region_slug: Optional[str] = None) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    # Add region column
    if region_slug is None:
        region_slug = find_region_slug(csv_path)
    df["region"] = region_slug

    # Coerce common numeric fields
    numeric_cols = [
        "population",
        "elevation",
        "elevation_confidence",
        "distance_km_to_perimeter",
        "driving_km_to_airport",
        "driving_km_to_hospital",
        "driving_time_minutes_to_airport",
        "driving_time_minutes_to_hospital",
        "nearest_hospital_km",
        "peaks_higher1200_within30km_count",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Normalize region-distance column to a generic name for convenience
    region_distance_cols = [c for c in df.columns if c.startswith("distance_km_to_") and c not in ("distance_km_to_perimeter",)]
    if region_distance_cols:
        # Use the first matching column (there should typically be exactly one)
        df["distance_km_to_region"] = pd.to_numeric(df[region_distance_cols[0]], errors="coerce")
    else:
        # Fallback: use perimeter distance if region-specific not present
        if "distance_km_to_perimeter" in df.columns:
            df["distance_km_to_region"] = pd.to_numeric(df["distance_km_to_perimeter"], errors="coerce")

    return df


def discover_csvs(outputs_dir: Path) -> List[Path]:
    """Find regional *_cities.csv files under outputs_dir.

    Excludes:
    - cache folders
    - ignore_test_run
    - aggregate/combined folders such as all_mountains, all_regions, combined
    - any folder not in the known region registry
    """
    from .config import REGIONS

    known_region_slugs = set(REGIONS.keys())
    aggregate_folders = {"all_mountains", "all_regions", "combined"}

    candidates: List[Path] = []
    # Recurse and collect
    for path in outputs_dir.rglob("*_cities.csv"):
        parts = list(path.parts)
        parts_lower = [p.lower() for p in parts]
        if any(seg in parts_lower for seg in ("cache", "ignore_test_run")):
            continue

        # Identify folder directly under outputs
        try:
            outputs_idx = parts_lower.index("outputs")
        except ValueError:
            # Not under outputs; skip
            continue
        region_folder = parts_lower[outputs_idx + 1] if outputs_idx + 1 < len(parts_lower) else path.parent.name.lower()

        # Skip aggregate folders and non-region folders
        if region_folder in aggregate_folders:
            continue
        if region_folder not in known_region_slugs:
            continue

        candidates.append(path)

    return sorted(candidates)


def make_plots(df: pd.DataFrame, out_dir: Path) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    out_dir.mkdir(parents=True, exist_ok=True)
    # Exclude aggregate folders to avoid duplicated points in plots
    if "region" in df.columns:
        df = df[~df["region"].isin({"all_mountains", "combined"})].copy()
    plot_style = {
        "s": 30,
        "alpha": 0.7,
        "linewidth": 0,
    }

    # Scatter 1: driving time to hospital vs airport
    cols_needed = ["driving_time_minutes_to_hospital", "driving_time_minutes_to_airport"]
    df1 = df.dropna(subset=cols_needed).copy()
    if not df1.empty:
        plt.figure(figsize=(8, 6))
        sns.scatterplot(
            data=df1,
            x="driving_time_minutes_to_hospital",
            y="driving_time_minutes_to_airport",
            hue="region",
            **plot_style,
        )
        plt.xlabel("Driving time to hospital (minutes)")
        plt.ylabel("Driving time to airport (minutes)")
        plt.title("Cities: Hospital vs Airport Driving Time")
        plt.legend(title="Region", bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.tight_layout()
        plt.savefig(out_dir / "scatter_hospital_time_vs_airport_time.png", dpi=150)
        plt.close()

    # Scatter 2: peaks count vs driving time to airport
    cols_needed = ["peaks_higher1200_within30km_count", "driving_time_minutes_to_airport"]
    df2 = df.dropna(subset=cols_needed).copy()
    if not df2.empty:
        plt.figure(figsize=(8, 6))
        sns.scatterplot(
            data=df2,
            x="peaks_higher1200_within30km_count",
            y="driving_time_minutes_to_airport",
            hue="region",
            **plot_style,
        )
        plt.xlabel("# Peaks ≥1200m within 30 km (relative to city)")
        plt.ylabel("Driving time to airport (minutes)")
        plt.title("Cities: Peaks vs Airport Driving Time")
        plt.legend(title="Region", bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.tight_layout()
        plt.savefig(out_dir / "scatter_peaks_count_vs_airport_time.png", dpi=150)
        plt.close()

    # Scatter 3: population vs peaks count
    cols_needed = ["population", "peaks_higher1200_within30km_count"]
    df3 = df.dropna(subset=cols_needed).copy()
    if not df3.empty:
        plt.figure(figsize=(8, 6))
        sns.scatterplot(
            data=df3,
            x="population",
            y="peaks_higher1200_within30km_count",
            hue="region",
            **plot_style,
        )
        plt.xscale("log")
        plt.xlabel("Population (log scale)")
        plt.ylabel("# Peaks ≥1200m within 30 km")
        plt.title("Cities: Population vs Peaks")
        plt.legend(title="Region", bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.tight_layout()
        plt.savefig(out_dir / "scatter_population_vs_peaks_count.png", dpi=150)
        plt.close()


def make_plots_interactive(df: pd.DataFrame, out_dir: Path) -> None:
    import plotly.express as px

    out_dir.mkdir(parents=True, exist_ok=True)
    # Exclude aggregate folders to avoid duplicated points in plots
    if "region" in df.columns:
        df = df[~df["region"].isin({"all_mountains", "combined"})].copy()

    common_hover = {
        "hover_name": "name",
        "hover_data": {
            "country": True,
            "population": True,
            "elevation": True,
            "driving_km_to_airport": True,
            "driving_km_to_hospital": True,
        },
        "color": "region",
    }

    # Interactive 1: driving time to hospital vs airport
    cols_needed = ["driving_time_minutes_to_hospital", "driving_time_minutes_to_airport", "name"]
    df1 = df.dropna(subset=cols_needed).copy()
    if not df1.empty:
        fig = px.scatter(
            df1,
            x="driving_time_minutes_to_hospital",
            y="driving_time_minutes_to_airport",
            **common_hover,
            title="Cities: Hospital vs Airport Driving Time (interactive)",
        )
        fig.update_traces(marker=dict(size=7, opacity=0.75))
        fig.write_html(out_dir / "scatter_hospital_time_vs_airport_time.html", include_plotlyjs="cdn")

    # Interactive 2: peaks count vs driving time to airport
    cols_needed = ["peaks_higher1200_within30km_count", "driving_time_minutes_to_airport", "name"]
    df2 = df.dropna(subset=cols_needed).copy()
    if not df2.empty:
        fig = px.scatter(
            df2,
            x="peaks_higher1200_within30km_count",
            y="driving_time_minutes_to_airport",
            **common_hover,
            title="Cities: Peaks vs Airport Driving Time (interactive)",
        )
        fig.update_traces(marker=dict(size=7, opacity=0.75))
        fig.write_html(out_dir / "scatter_peaks_count_vs_airport_time.html", include_plotlyjs="cdn")

    # Interactive 3: population vs peaks count
    cols_needed = ["population", "peaks_higher1200_within30km_count", "name"]
    df3 = df.dropna(subset=cols_needed).copy()
    if not df3.empty:
        fig = px.scatter(
            df3,
            x="population",
            y="peaks_higher1200_within30km_count",
            **common_hover,
            title="Cities: Population vs Peaks (interactive)",
            log_x=True,
        )
        fig.update_traces(marker=dict(size=7, opacity=0.75))
        fig.write_html(out_dir / "scatter_population_vs_peaks_count.html", include_plotlyjs="cdn")


def extra_analyses(df: pd.DataFrame, out_dir: Path) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    out_dir.mkdir(parents=True, exist_ok=True)

    # Summary by region
    numeric_summary_cols = [
        "population",
        "elevation",
        "distance_km_to_region",
        "driving_km_to_airport",
        "driving_km_to_hospital",
        "driving_time_minutes_to_airport",
        "driving_time_minutes_to_hospital",
        "nearest_hospital_km",
        "peaks_higher1200_within30km_count",
    ]
    present = [c for c in numeric_summary_cols if c in df.columns]
    if present:
        summary_by_region = df.groupby("region")[present].agg(["count", "mean", "median", "min", "max"]).round(2)
        # Flatten MultiIndex columns
        summary_by_region.columns = ["_".join(col).strip("_") for col in summary_by_region.columns.values]
        summary_by_region.to_csv(out_dir / "summary_by_region.csv")

    # Correlation heatmap (numeric columns only)
    numeric_df = df.select_dtypes(include=[np.number]).copy()
    if not numeric_df.empty:
        corr = numeric_df.corr(numeric_only=True)
        plt.figure(figsize=(10, 8))
        sns.heatmap(corr, cmap="vlag", center=0, annot=False)
        plt.title("Correlation Heatmap (numeric columns)")
        plt.tight_layout()
        plt.savefig(out_dir / "correlation_heatmap.png", dpi=150)
        plt.close()


def combine(outputs_dir: Path, out_dir: Path) -> Path:
    csv_paths = discover_csvs(outputs_dir)
    if not csv_paths:
        raise FileNotFoundError(f"No '*_cities.csv' files found under {outputs_dir}")

    frames: List[pd.DataFrame] = []
    for path in csv_paths:
        region_slug = find_region_slug(path)
        frames.append(load_and_standardize_csv(path, region_slug))

    combined = pd.concat(frames, ignore_index=True, sort=False)

    # Guard: drop duplicates that might arise from overlapping inputs
    # Use a stable city key based on name and coordinates
    for col in ("name", "latitude", "longitude"):
        if col not in combined.columns:
            combined[col] = combined.get(col, "")
    combined["__key"] = (
        combined["name"].astype(str).str.strip()
        + "|"
        + combined["latitude"].astype(str).str.strip()
        + "|"
        + combined["longitude"].astype(str).str.strip()
    )
    before = len(combined)
    combined = combined.drop_duplicates(subset="__key").drop(columns=["__key"])  # keep first occurrence

    out_dir.mkdir(parents=True, exist_ok=True)
    combined_csv = out_dir / "all_regions_cities.csv"
    combined.to_csv(combined_csv, index=False)

    # Generate plots and extra analyses
    make_plots(combined, out_dir)
    make_plots_interactive(combined, out_dir)
    extra_analyses(combined, out_dir)

    return combined_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Combine regional city CSVs and generate analyses/plots.")
    parser.add_argument("--outputs-dir", type=str, default="outputs", help="Root outputs directory containing region subdirs")
    parser.add_argument("--out-dir", type=str, default="outputs/combined", help="Directory to write combined CSV and plots")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs_dir = Path(args.outputs_dir)
    out_dir = Path(args.out_dir)
    combined_csv = combine(outputs_dir, out_dir)
    print(f"Wrote combined CSV to {combined_csv}")


if __name__ == "__main__":
    main()


