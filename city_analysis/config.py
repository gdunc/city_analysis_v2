from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


ALPINE_COUNTRIES = [
    "AT",  # Austria
    "FR",  # France
    "IT",  # Italy
    "DE",  # Germany
    "CH",  # Switzerland
]

DEFAULT_MIN_POPULATION = 5000
DEFAULT_REQUIRE_OSM_POPULATION = False


@dataclass
class RegionSettings:
    """Configuration describing a mountain region analysis target.

    Attributes:
        name: Human-readable name of the region
        slug: Short identifier for filenames and output folders
        countries: Default list of ISO 3166-1 alpha-2 country codes to include
        perimeter_geojson: Optional path to a GeoJSON file for the region perimeter
        excluded_countries: Optional list of ISO codes to exclude (legacy Alps behavior)
        map_tiles: Default base map tiles name for Folium
        min_population: Default population threshold
        require_osm_population: Whether to require population tag for OSM places
    """

    name: str
    slug: str
    countries: List[str]
    perimeter_geojson: Optional[Path] = None
    excluded_countries: List[str] = field(default_factory=list)
    map_tiles: str = "OpenTopoMap"
    min_population: int = DEFAULT_MIN_POPULATION
    require_osm_population: bool = DEFAULT_REQUIRE_OSM_POPULATION


def _project_root() -> Path:
    return Path(__file__).parent.parent


# Built-in region registry
REGIONS: dict[str, RegionSettings] = {
    "alps": RegionSettings(
        name="Alps",
        slug="alps",
        countries=ALPINE_COUNTRIES,
        # Use existing project-root GeoJSON if present
        perimeter_geojson=(_project_root() / "alps_perimeter.geojson"),
        # Exclude only Slovenia and Liechtenstein (Switzerland now included)
        excluded_countries=["SI", "LI"],
        map_tiles="OpenTopoMap",
    ),
    "pyrenees": RegionSettings(
        name="Pyrenees",
        slug="pyrenees",
        countries=["FR", "ES", "AD"],
        # Expected future location for curated polygon (optional)
        perimeter_geojson=None,
        excluded_countries=[],
        map_tiles="OpenTopoMap",
    ),
    "rockies": RegionSettings(
        name="Rocky Mountains",
        slug="rockies",
        countries=["US", "CA"],
        # Perimeter discovered at data/regions/rockies/perimeter.geojson if present
        perimeter_geojson=None,
        excluded_countries=[],
        map_tiles="OpenTopoMap",
    ),
    "sierra_nevada": RegionSettings(
        name="Sierra Nevada",
        slug="sierra_nevada",
        countries=["US", "MX"],
        # Expect perimeter at data/regions/sierra_nevada/perimeter.geojson if present
        perimeter_geojson=None,
        excluded_countries=[],
        map_tiles="OpenTopoMap",
    ),
    "cascade_range": RegionSettings(
        name="Cascade Range",
        slug="cascade_range",
        countries=["US", "CA"],
        # Expect perimeter at data/regions/cascade_range/perimeter.geojson if present
        perimeter_geojson=None,
        excluded_countries=[],
        map_tiles="OpenTopoMap",
    ),
    "coast_mountains": RegionSettings(
        name="Coast Mountains",
        slug="coast_mountains",
        countries=["US", "CA"],
        # Expect perimeter at data/regions/coast_mountains/perimeter.geojson if present
        perimeter_geojson=None,
        excluded_countries=[],
        map_tiles="OpenTopoMap",
    ),
}


def load_region_settings(slug: str) -> RegionSettings:
    key = (slug or "").strip().lower()
    if key in REGIONS:
        return REGIONS[key]
    # Default to Alps if unknown
    return REGIONS["alps"]


def load_region_settings_from_yaml(yaml_path: str | Path) -> RegionSettings:
    """Load RegionSettings from a YAML file.

    The YAML can include keys: name, slug, countries, perimeter_geojson,
    excluded_countries, map_tiles, min_population, require_osm_population.
    """
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise RuntimeError("PyYAML is required to load region YAML configs. Install pyyaml.") from e

    path = Path(yaml_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _list_str(v) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)]

    rs = RegionSettings(
        name=str(data.get("name", data.get("slug", "Region"))),
        slug=str(data.get("slug", "region")),
        countries=_list_str(data.get("countries", [])) or ALPINE_COUNTRIES,
        perimeter_geojson=(Path(str(data["perimeter_geojson"])) if data.get("perimeter_geojson") else None),
        excluded_countries=_list_str(data.get("excluded_countries", [])),
        map_tiles=str(data.get("map_tiles", "OpenStreetMap")),
        min_population=int(data.get("min_population", DEFAULT_MIN_POPULATION)),
        require_osm_population=bool(data.get("require_osm_population", DEFAULT_REQUIRE_OSM_POPULATION)),
    )
    return rs
