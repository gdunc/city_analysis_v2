from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .combine_analyze import combine


def ensure_combined_csv(outputs_dir: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    combined_csv = out_dir / "all_regions_cities.csv"
    if not combined_csv.exists():
        combine(outputs_dir, out_dir)
    return combined_csv


def load_data(outputs_dir: Path, out_dir: Path) -> pd.DataFrame:
    csv_path = ensure_combined_csv(outputs_dir, out_dir)
    df = pd.read_csv(csv_path)

    # Coerce expected numeric columns (lenient)
    numeric_cols = [
        "population",
        "elevation",
        "driving_km_to_airport",
        "driving_km_to_hospital",
        "driving_time_minutes_to_airport",
        "driving_time_minutes_to_hospital",
        "peaks_higher1200_within30km_count",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Basic sanitization
    if "region" not in df.columns:
        df["region"] = "unknown"
    if "country" not in df.columns:
        df["country"] = ""
    if "name" not in df.columns:
        df["name"] = "(unknown)"

    return df


def compute_ranges(df: pd.DataFrame) -> Dict[str, Tuple[float, float]]:
    ranges: Dict[str, Tuple[float, float]] = {}
    for col in [
        "population",
        "elevation",
        "driving_time_minutes_to_hospital",
        "driving_time_minutes_to_airport",
        "peaks_higher1200_within30km_count",
    ]:
        if col in df.columns:
            s = df[col].dropna()
            if not s.empty:
                ranges[col] = (float(s.min()), float(s.max()))
    return ranges


def create_app(df: pd.DataFrame):
    from dash import Dash, Input, Output, dcc, html
    import plotly.express as px

    app = Dash(__name__)

    ranges = compute_ranges(df)
    regions = sorted([x for x in df["region"].dropna().unique()])
    countries = sorted([x for x in df["country"].dropna().unique()])

    def range_slider(id_: str, label: str, key: str):
        if key not in ranges:
            return html.Div([
                html.Label(f"{label} (not available)"),
            ])
        rmin, rmax = ranges[key]
        # Use reasonable steps for big ranges
        step = max((rmax - rmin) / 100.0, 1.0)
        return html.Div([
            html.Label(label),
            dcc.RangeSlider(
                id=id_,
                min=rmin,
                max=rmax,
                value=[rmin, rmax],
                step=step,
                tooltip={"placement": "bottom", "always_visible": False},
                allowCross=False,
            )
        ], style={"marginBottom": "20px"})

    app.layout = html.Div([
        html.H2("City Analysis – Interactive Filters"),
        html.Div([
            html.Div([
                html.Label("Region"),
                dcc.Dropdown(
                    id="region_filter",
                    options=[{"label": r, "value": r} for r in regions],
                    multi=True,
                    placeholder="All regions",
                ),
                html.Label("Country"),
                dcc.Dropdown(
                    id="country_filter",
                    options=[{"label": c, "value": c} for c in countries],
                    multi=True,
                    placeholder="All countries",
                ),
                range_slider("pop_range", "Population", "population"),
                range_slider("elev_range", "Elevation (m)", "elevation"),
                range_slider("t_hosp_range", "Driving time to hospital (min)", "driving_time_minutes_to_hospital"),
                range_slider("t_air_range", "Driving time to airport (min)", "driving_time_minutes_to_airport"),
                range_slider("peaks_range", "# Peaks ≥1200m within 30 km", "peaks_higher1200_within30km_count"),
            ], style={"flex": "0 0 320px", "paddingRight": "24px"}),
            html.Div([
                dcc.Graph(id="g1", config={"displaylogo": False}),
                dcc.Graph(id="g2", config={"displaylogo": False}),
                dcc.Graph(id="g3", config={"displaylogo": False}),
            ], style={"flex": "1 1 auto"}),
        ], style={"display": "flex"})
    ], style={"padding": "16px"})

    @app.callback(
        Output("g1", "figure"),
        Output("g2", "figure"),
        Output("g3", "figure"),
        Input("region_filter", "value"),
        Input("country_filter", "value"),
        Input("pop_range", "value"),
        Input("elev_range", "value"),
        Input("t_hosp_range", "value"),
        Input("t_air_range", "value"),
        Input("peaks_range", "value"),
    )
    def update_plots(region_sel, country_sel, pop_r, elev_r, t_hosp_r, t_air_r, peaks_r):  # type: ignore[no-redef]
        fdf = df.copy()

        def apply_range(col: str, rng):
            if col in fdf.columns and isinstance(rng, (list, tuple)) and len(rng) == 2:
                fdf[col] = pd.to_numeric(fdf[col], errors="coerce")
                fdf.dropna(subset=[col], inplace=True)
                fdf = fdf[(fdf[col] >= rng[0]) & (fdf[col] <= rng[1])]
            return fdf

        # Categorical filters
        if region_sel:
            fdf = fdf[fdf["region"].isin(region_sel)]
        if country_sel:
            fdf = fdf[fdf["country"].isin(country_sel)]

        # Range filters
        fdf = apply_range("population", pop_r)
        fdf = apply_range("elevation", elev_r)
        fdf = apply_range("driving_time_minutes_to_hospital", t_hosp_r)
        fdf = apply_range("driving_time_minutes_to_airport", t_air_r)
        fdf = apply_range("peaks_higher1200_within30km_count", peaks_r)

        # Figure 1: hospital vs airport time
        g1 = px.scatter(
            fdf.dropna(subset=["driving_time_minutes_to_hospital", "driving_time_minutes_to_airport"]),
            x="driving_time_minutes_to_hospital",
            y="driving_time_minutes_to_airport",
            color="region",
            hover_name="name",
            hover_data={
                "country": True,
                "population": True,
                "elevation": True,
                "driving_km_to_airport": True,
                "driving_km_to_hospital": True,
            },
            title="Hospital vs Airport Driving Time",
        )
        g1.update_traces(marker=dict(size=8, opacity=0.8))

        # Figure 2: peaks vs airport time
        g2 = px.scatter(
            fdf.dropna(subset=["peaks_higher1200_within30km_count", "driving_time_minutes_to_airport"]),
            x="peaks_higher1200_within30km_count",
            y="driving_time_minutes_to_airport",
            color="region",
            hover_name="name",
            hover_data={
                "country": True,
                "population": True,
                "elevation": True,
                "driving_km_to_airport": True,
                "driving_km_to_hospital": True,
            },
            title="Peaks vs Airport Driving Time",
        )
        g2.update_traces(marker=dict(size=8, opacity=0.8))

        # Figure 3: population vs peaks (log-x)
        g3 = px.scatter(
            fdf.dropna(subset=["population", "peaks_higher1200_within30km_count"]),
            x="population",
            y="peaks_higher1200_within30km_count",
            color="region",
            hover_name="name",
            hover_data={
                "country": True,
                "elevation": True,
                "driving_time_minutes_to_airport": True,
                "driving_time_minutes_to_hospital": True,
            },
            title="Population vs Peaks",
            log_x=True,
        )
        g3.update_traces(marker=dict(size=8, opacity=0.8))

        return g1, g2, g3

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Dash app for filtered interactive city plots.")
    parser.add_argument("--outputs-dir", type=str, default="outputs", help="Root outputs directory")
    parser.add_argument("--out-dir", type=str, default="outputs/combined", help="Directory with combined CSV")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8050, help="Port to serve")
    parser.add_argument("--debug", action="store_true", help="Enable Dash debug mode")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs_dir = Path(args.outputs_dir)
    out_dir = Path(args.out_dir)
    df = load_data(outputs_dir, out_dir)
    app = create_app(df)
    app.run_server(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()


