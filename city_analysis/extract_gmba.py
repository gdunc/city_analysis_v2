from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import argparse
import geopandas as gpd


def _project_root() -> Path:
    return Path(__file__).parent.parent


def _match_any_name_columns(gdf: gpd.GeoDataFrame, query: str) -> gpd.GeoDataFrame:
    """Return subset of rows whose name-like columns contain the query substring (case-insensitive)."""
    col_candidates: List[str] = [
        "Name_EN",
        "AsciiName",
        "MapName",
        "DBaseName",
        "MtnSysName",
        "NAME",
        "NAME_EN",
        "SYSTEM",
        "MtnName",
        "MtnSys",
    ]
    present = [c for c in col_candidates if c in gdf.columns]
    if not present:
        raise RuntimeError(
            f"Could not find expected GMBA name columns. Columns present: {list(gdf.columns)}"
        )
    mask = None
    for c in present:
        m = gdf[c].astype(str).str.contains(query, case=False, na=False)
        mask = m if mask is None else (mask | m)
    return gdf[mask].copy()


def _restrict_countries(gdf: gpd.GeoDataFrame, allowlist: Optional[Iterable[str]]) -> gpd.GeoDataFrame:
    if not allowlist:
        return gdf
    allow = {s.upper() for s in allowlist}
    # Expand common synonyms/3-letter codes and names
    expanded = set(allow)
    def _add_synonyms(code: str, variants: Iterable[str]):
        if code in allow:
            for v in variants:
                expanded.add(v)
    _add_synonyms("US", ["USA", "UNITED STATES", "UNITED STATES OF AMERICA"])
    _add_synonyms("CA", ["CAN", "CANADA"])
    _add_synonyms("MX", ["MEX", "MEXICO"])
    _add_synonyms("ES", ["ESP", "SPAIN"])
    _add_synonyms("FR", ["FRA", "FRANCE"])
    _add_synonyms("AD", ["ANDORRA"])
    allow = expanded
    country_cols = [
        c for c in (
            "CountryISO",
            "Countries",
            "CC",
            "ISO",
            "COUNTRY",
            "adm0_a3",
            "adm0_iso",
        )
        if c in gdf.columns
    ]
    if not country_cols:
        return gdf

    def _row_any_allowed(row) -> bool:
        for cc in country_cols:
            v = str(row.get(cc, "")).upper()
            parts = [p.strip() for p in v.replace(";", ",").split(",") if p.strip()]
            for p in parts or [v]:
                if p in allow:
                    return True
        return False

    out = gdf[gdf.apply(_row_any_allowed, axis=1)]
    return out


def extract_gmba_region(
    gmba_shapefile: Path,
    out_dir: Path,
    name_query: str,
    country_allowlist: Optional[Iterable[str]] = None,
    simplify_tolerance_m: float = 150.0,
    buffer_m: Optional[float] = 10000.0,
) -> Tuple[Path, Optional[Path]]:
    """Extract a named mountain region perimeter from GMBA v2, dissolve, simplify, and save.

    Returns:
        Tuple of (perimeter_path, buffer_path_or_None)
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    gdf = gpd.read_file(gmba_shapefile)
    candidates = _match_any_name_columns(gdf, name_query)
    if candidates.empty:
        raise RuntimeError(f"No GMBA features matched '{name_query}'. Please verify the dataset.")

    candidates = _restrict_countries(candidates, country_allowlist)
    if candidates.empty:
        raise RuntimeError(
            f"All '{name_query}' candidates filtered out by country restriction ({list(country_allowlist or [])})."
        )

    if candidates.crs is None:
        candidates.set_crs(4326, inplace=True)
    dissolved = candidates.to_crs(3857).dissolve().geometry.iloc[0]
    simplified = dissolved.simplify(simplify_tolerance_m, preserve_topology=True)

    # Save perimeter in WGS84
    perimeter_wgs84 = gpd.GeoSeries([simplified], crs=3857).to_crs(4326).iloc[0]
    out_perimeter = out_dir / "perimeter.geojson"
    gpd.GeoSeries([perimeter_wgs84], crs=4326).to_file(out_perimeter, driver="GeoJSON")

    out_buffer = None
    if buffer_m and buffer_m > 0:
        buffered = gpd.GeoSeries([simplified], crs=3857).buffer(buffer_m).iloc[0]
        buffered_wgs84 = gpd.GeoSeries([buffered], crs=3857).to_crs(4326).iloc[0]
        out_buffer = out_dir / "perimeter_buffer_10km.geojson"
        gpd.GeoSeries([buffered_wgs84], crs=4326).to_file(out_buffer, driver="GeoJSON")

    return out_perimeter, out_buffer


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract a GMBA mountain system perimeter by name")
    p.add_argument("--gmba", type=str, default=str(_project_root() / "GMBA_Inventory_v2.0_standard" / "GMBA_Inventory_v2.0_standard.shp"), help="Path to GMBA v2 standard shapefile")
    p.add_argument("--out-dir", type=str, required=True, help="Output directory for region (e.g., data/regions/sierra_nevada)")
    p.add_argument("--name", type=str, required=True, help="Substring to match in GMBA name columns (e.g., 'Sierra Nevada')")
    p.add_argument("--countries", nargs="*", default=None, help="Restrict to ISO country codes (e.g., US CA ES FR)")
    p.add_argument("--simplify-m", type=float, default=150.0, help="Simplification tolerance in meters (metric CRS)")
    p.add_argument("--buffer-m", type=float, default=10000.0, help="Optional buffer distance in meters for companion buffer file")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    gmba = Path(args.gmba)
    out_dir = Path(args.out_dir)
    countries = args.countries or None
    buffer_m: Optional[float] = float(args.buffer_m) if args.buffer_m and args.buffer_m > 0 else None
    p, b = extract_gmba_region(
        gmba_shapefile=gmba,
        out_dir=out_dir,
        name_query=args.name,
        country_allowlist=countries,
        simplify_tolerance_m=float(args.simplify_m),
        buffer_m=buffer_m,
    )
    print(f"Wrote: {p}")
    if b:
        print(f"Wrote: {b}")


if __name__ == "__main__":
    main()


