from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import geopandas as gpd


def _project_root() -> Path:
    return Path(__file__).parent.parent


def extract_rockies(
    gmba_shapefile: Path,
    out_dir: Path,
    simplify_tolerance_m: float = 150.0,
    buffer_m: Optional[float] = 10000.0,
) -> Tuple[Path, Optional[Path]]:
    """Extract a Rockies perimeter from GMBA v2, dissolve, simplify, and save.

    Returns:
        Tuple of (perimeter_path, buffer_path_or_None)
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read GMBA standard inventory; rely on installed vector drivers (pyogrio/fiona)
    gdf = gpd.read_file(gmba_shapefile)

    # Identify possible name columns and match on "Rocky"
    col_candidates = [
        # Observed in this dataset snapshot
        "Name_EN",
        "AsciiName",
        "MapName",
        "DBaseName",
        # Other possible variants
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
            f"Could not find expected GMBA name columns in {gmba_shapefile}. Columns: {list(gdf.columns)}"
        )

    mask = None
    for c in present:
        m = gdf[c].astype(str).str.contains("Rocky", case=False, na=False)
        mask = m if mask is None else (mask | m)
    candidates = gdf[mask].copy()
    if candidates.empty:
        raise RuntimeError("No GMBA features matched 'Rocky' by name. Please verify schema.")

    # Restrict to US/CA if country attributes exist
    country_cols = [c for c in ("CountryISO", "Countries", "CC", "ISO", "COUNTRY", "adm0_a3", "adm0_iso") if c in candidates.columns]
    if country_cols:
        def _is_us_ca(row) -> bool:
            for cc in country_cols:
                v = str(row.get(cc, "")).upper()
                # Handle comma-separated lists in CountryISO/Countries
                parts = [p.strip() for p in v.replace(";", ",").split(",") if p.strip()]
                for p in parts or [v]:
                    if p in ("US", "USA", "CA", "CAN", "UNITED STATES", "CANADA"):
                        return True
            return False
        candidates = candidates[candidates.apply(_is_us_ca, axis=1)]
        if candidates.empty:
            raise RuntimeError("All Rocky* candidates filtered out by country restriction (US/CA).")

    # Dissolve to one geometry in a metric CRS, then simplify
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


if __name__ == "__main__":
    gmba = _project_root() / "GMBA_Inventory_v2.0_standard" / "GMBA_Inventory_v2.0_standard.shp"
    out = _project_root() / "data" / "regions" / "rockies"
    p, b = extract_rockies(gmba, out)
    print(f"Wrote: {p}")
    if b:
        print(f"Wrote: {b}")


