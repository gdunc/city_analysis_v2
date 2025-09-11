from __future__ import annotations

from typing import Dict, Iterable, Optional
from pathlib import Path

import folium
from folium.plugins import MarkerCluster


def _compute_map_center(records: Iterable[Dict]) -> tuple[float, float]:
    items = list(records)
    if not items:
        # Default to central Alps
        return (46.8, 10.8)
    avg_lat = sum(float(r.get("latitude", 0.0) or 0.0) for r in items) / len(items)
    avg_lon = sum(float(r.get("longitude", 0.0) or 0.0) for r in items) / len(items)
    return (avg_lat, avg_lon)


def _popup_html(r: Dict) -> str:
    name = r.get("name", "Unknown")
    country = r.get("country", "")
    population = r.get("population")
    elevation = r.get("elevation")
    elev_src = r.get("elevation_source")
    dist_km = r.get("distance_km_to_alps")
    source = r.get("source")

    parts = [f"<b>{name}</b>"]
    if country:
        parts.append(f"({country})")
    if population is not None:
        try:
            pop_int = int(population)
            parts.append(f"<br/>Population: {pop_int:,}")
        except Exception:
            parts.append(f"<br/>Population: {population}")
    if elevation is not None:
        try:
            elev_num = float(elevation)
            parts.append(f"<br/>Elevation: {elev_num:.0f} m")
        except Exception:
            parts.append(f"<br/>Elevation: {elevation} m")
    if dist_km is not None:
        try:
            parts.append(f"<br/>Dist to Alps: {float(dist_km):.1f} km")
        except Exception:
            parts.append(f"<br/>Dist to Alps: {dist_km} km")
    if source:
        parts.append(f"<br/>Source: {source}")
    if elev_src:
        parts.append(f" <i>({elev_src})</i>")
    return "".join(parts)


def _marker_color(population_value: Optional[int | float]) -> str:
    try:
        pop = float(population_value) if population_value is not None else 0.0
    except Exception:
        pop = 0.0
    # Simple population tiers
    if pop >= 100000:
        return "darkred"
    if pop >= 50000:
        return "red"
    if pop >= 20000:
        return "orange"
    if pop >= 10000:
        return "green"
    return "blue"


def build_map(records: Iterable[Dict], tiles: str = "OpenStreetMap") -> folium.Map:
    records_list = list(records)
    center = _compute_map_center(records_list)
    fmap = folium.Map(location=center, zoom_start=7, tiles=tiles, control_scale=True)

    cluster = MarkerCluster(name="Cities").add_to(fmap)

    for r in records_list:
        try:
            lat = float(r["latitude"])  # required
            lon = float(r["longitude"])  # required
        except Exception:
            continue
        popup = folium.Popup(_popup_html(r), max_width=350)
        color = _marker_color(r.get("population"))
        # Attach population as a data attribute for client-side filtering
        folium.CircleMarker(
            location=(lat, lon),
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            popup=popup,
            tooltip=None,
            # custom attributes passed via options; Leaflet keeps them on layer.options
            **{"population": r.get("population", 0)}
        ).add_to(cluster)

    folium.LayerControl().add_to(fmap)
    # Inject a simple population filter UI and JS
    _inject_population_filter(fmap)
    return fmap


def save_map(records: Iterable[Dict], out_path: str | Path, tiles: str = "OpenStreetMap") -> Path:
    fmap = build_map(records, tiles=tiles)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Render and post-process to avoid object spread for broader browser support
    html = fmap.get_root().render()
    html = _strip_object_spread_in_html(html)
    out_path.write_text(html, encoding="utf-8")
    return out_path


# --- Country-colored, population-sized map ---

def _country_color_map(countries: Iterable[str]) -> Dict[str, str]:
    palette = [
        "red", "blue", "green", "purple", "orange", "darkred", "lightred",
        "beige", "darkblue", "darkgreen", "cadetblue", "darkpurple", "white",
        "pink", "lightblue", "lightgreen", "gray", "black", "lightgray",
    ]
    unique = [c for c in dict.fromkeys([c or "UNK" for c in countries])]
    mapping: Dict[str, str] = {}
    for idx, c in enumerate(unique):
        mapping[c] = palette[idx % len(palette)]
    return mapping


def _population_bounds(records: Iterable[Dict]) -> tuple[float, float]:
    pops: list[float] = []
    for r in records:
        v = r.get("population")
        try:
            f = float(v)
            if f > 0:
                pops.append(f)
        except Exception:
            continue
    if not pops:
        return (1.0, 1.0)
    return (min(pops), max(pops))


def _scaled_radius(pop_value: Optional[float | int], min_pop: float, max_pop: float, min_r: float = 3.0, max_r: float = 14.0) -> float:
    try:
        p = float(pop_value)
        if p <= 0:
            return min_r
    except Exception:
        return min_r
    if max_pop <= min_pop:
        return (min_r + max_r) / 2.0
    # Log-scale to avoid huge cities dominating
    import math
    lp = math.log10(max(p, 1.0))
    lmin = math.log10(max(min_pop, 1.0))
    lmax = math.log10(max(max_pop, 1.0))
    t = (lp - lmin) / (lmax - lmin) if lmax > lmin else 0.5
    return min_r + t * (max_r - min_r)


def build_country_color_population_sized_map(records: Iterable[Dict], tiles: str = "OpenStreetMap") -> folium.Map:
    items = list(records)
    center = _compute_map_center(items)
    fmap = folium.Map(location=center, zoom_start=7, tiles=tiles, control_scale=True)

    # Prepare color mapping and population scaling
    countries = [str(r.get("country") or "UNK") for r in items]
    color_map = _country_color_map(countries)
    min_pop, max_pop = _population_bounds(items)

    # Group markers by country with separate clusters for toggling via LayerControl
    from collections import defaultdict
    by_country: Dict[str, list[Dict]] = defaultdict(list)
    for r in items:
        key = str(r.get("country") or "UNK")
        by_country[key].append(r)

    for country, recs in sorted(by_country.items(), key=lambda kv: kv[0]):
        group = folium.FeatureGroup(name=f"{country} ({len(recs)})")
        cluster = MarkerCluster().add_to(group)
        color = color_map.get(country, "blue")
        for r in recs:
            try:
                lat = float(r["latitude"])  # required
                lon = float(r["longitude"])  # required
            except Exception:
                continue
            radius = _scaled_radius(r.get("population"), min_pop, max_pop)
            popup = folium.Popup(_popup_html(r), max_width=350)
            # Attach population as a data attribute for client-side filtering
            folium.CircleMarker(
                location=(lat, lon),
                radius=radius,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                popup=popup,
                tooltip=None,
                **{"population": r.get("population", 0)}
            ).add_to(cluster)
        group.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)
    _inject_population_filter(fmap)
    return fmap


def save_country_map(records: Iterable[Dict], out_path: str | Path, tiles: str = "OpenStreetMap") -> Path:
    fmap = build_country_color_population_sized_map(records, tiles=tiles)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = fmap.get_root().render()
    html = _strip_object_spread_in_html(html)
    out_path.write_text(html, encoding="utf-8")
    return out_path


# --- Client-side filter injection ---

def _inject_population_filter(fmap: folium.Map) -> None:
    """Add a minimal UI and JS to filter markers by minimum population.

    This scans all CircleMarkers (including those inside MarkerClusters and FeatureGroups)
    and toggles their visibility based on a user-entered threshold. It relies on each
    marker having a numeric `population` stored in `layer.options.population`.
    """
    # HTML control (top-left)
    html = (
        '<div id="pop-filter" style="background: white; padding: 8px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3);">\n           <label style="font-size:12px; display:block; margin-bottom:4px;">Min population</label>\n           <input id="pop-threshold" type="number" min="0" step="1000" value="0" style="width:140px;"/>\n           <button id="apply-pop-filter" style="margin-left:6px;">Apply</button>\n         </div>'
    )

    # No MacroElement: we'll create the control entirely in JS at runtime

    # JS to apply filter (handles MarkerCluster ownership)
    script = """
    (function(){
      var MAP_VAR_NAME = '%MAP%';
      function getMap(){ return window[MAP_VAR_NAME]; }

      function collectMarkers(layer, out){
        if (!layer) return;
        if (layer instanceof L.CircleMarker) {
          out.push(layer);
        } else if (layer.getLayers && typeof layer.getLayers === 'function') {
          var children = layer.getLayers();
          for (var i=0;i<children.length;i++) collectMarkers(children[i], out);
        } else if (layer.eachLayer && typeof layer.eachLayer === 'function') {
          layer.eachLayer(function(child){ collectMarkers(child, out); });
        }
      }

      function collectClusters(layer, out){
        if (!layer) return;
        if (typeof L.MarkerClusterGroup !== 'undefined' && (layer instanceof L.MarkerClusterGroup)) {
          out.push(layer);
        } else if (layer.getLayers && typeof layer.getLayers === 'function') {
          var children = layer.getLayers();
          for (var i=0;i<children.length;i++) collectClusters(children[i], out);
        } else if (layer.eachLayer && typeof layer.eachLayer === 'function') {
          layer.eachLayer(function(child){ collectClusters(child, out); });
        }
      }

      function readPopulation(marker){
        var p = 0;
        if (marker && marker.options && marker.options.population != null) {
          var n = Number(marker.options.population);
          if (!isNaN(n)) return n;
        }
        try {
          var pop = 0;
          var popup = marker.getPopup && marker.getPopup();
          var content = popup && (popup.getContent && popup.getContent());
          var htmlStr = '';
          if (typeof content === 'string') {
            htmlStr = content;
          } else if (content && typeof content.innerHTML === 'string') {
            htmlStr = content.innerHTML;
          } else if (content && typeof content.textContent === 'string') {
            htmlStr = content.textContent;
          }
          if (htmlStr) {
            var m = htmlStr.match(/Population:\s*([0-9,.]+)/i);
            if (m && m[1]) {
              pop = Number(m[1].replace(/[\,\s]/g, '')) || 0;
            }
          }
          return pop;
        } catch (e) { return 0; }
      }

      var state = window.__popFilterState || { indexBuilt:false, markerToOwners:{}, markers:[], clusters:[] };
      function buildIndex(){
        var map = getMap();
        state.markers = [];
        state.clusters = [];
        map.eachLayer(function(l){ collectMarkers(l, state.markers); });
        map.eachLayer(function(l){ collectClusters(l, state.clusters); });
        state.markerToOwners = {};
        for (var i=0;i<state.markers.length;i++){
          var m = state.markers[i];
          var owners = [];
          for (var j=0;j<state.clusters.length;j++){
            var c = state.clusters[j];
            if (c.hasLayer && c.hasLayer(m)) owners.push(c);
          }
          state.markerToOwners[m._leaflet_id] = owners;
        }
        state.indexBuilt = true;
        window.__popFilterState = state;
      }

      function showMarker(m){
        var map = getMap();
        var owners = state.markerToOwners[m._leaflet_id] || [];
        if (owners.length > 0){
          for (var i=0;i<owners.length;i++){
            var c = owners[i];
            if (!c.hasLayer(m)) c.addLayer(m);
          }
        } else {
          if (!map.hasLayer(m)) map.addLayer(m);
        }
        if (m._icon) m._icon.style.display = '';
        if (m._path) m._path.style.display = '';
      }

      function hideMarker(m){
        var map = getMap();
        var owners = state.markerToOwners[m._leaflet_id] || [];
        if (owners.length > 0){
          for (var i=0;i<owners.length;i++){
            var c = owners[i];
            if (c.hasLayer(m)) c.removeLayer(m);
          }
        } else {
          if (map.hasLayer(m)) map.removeLayer(m);
        }
        if (m._icon) m._icon.style.display = 'none';
        if (m._path) m._path.style.display = 'none';
      }

      function applyFilter(minPop){
        if (!state.indexBuilt) buildIndex();
        for (var i=0;i<state.markers.length;i++){
          var m = state.markers[i];
          var p = readPopulation(m);
          if (p >= minPop) showMarker(m); else hideMarker(m);
        }
      }

      function ensureUI(){
        // If control already present, skip
        if (document.getElementById('pop-filter')) return;
        var map = getMap();
        var ctrl = L.control({position: 'topleft'});
        ctrl.onAdd = function(map){
          var container = L.DomUtil.create('div');
          container.innerHTML = `
    """
    script += html
    script += """
          `;
          L.DomEvent.disableClickPropagation(container);
          return container;
        };
        ctrl.addTo(map);
      }

      function hookUI(){
        ensureUI();
        var btn = document.getElementById('apply-pop-filter');
        var input = document.getElementById('pop-threshold');
        if (!btn || !input) return;
        btn.addEventListener('click', function(){
          var v = Number(input.value || 0) || 0;
          applyFilter(v);
        });
        input.addEventListener('keypress', function(e){
          if (e.key === 'Enter') {
            var v = Number(input.value || 0) || 0;
            applyFilter(v);
          }
        });
      }

      function whenMapReady(fn){
        if (getMap()) { fn(); return; }
        var tries = 0; var maxTries = 200; // ~10s
        var iv = setInterval(function(){
          if (getMap()){ clearInterval(iv); fn(); }
          else if (++tries >= maxTries){ clearInterval(iv); }
        }, 50);
      }

      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function(){ whenMapReady(hookUI); });
      } else {
        whenMapReady(hookUI);
      }
    })();
    """
    from folium import Element
    script = script.replace("%MAP%", fmap.get_name())
    script = script.replace("{{", "{").replace("}}", "}")
    wrapped = "<script>{% raw %}" + script + "{% endraw %}</script>"
    fmap.get_root().html.add_child(Element(wrapped))


def _strip_object_spread_in_html(html: str) -> str:
    """Replace object spread syntax ...{a:b} with inline properties a:b in HTML JS blocks.

    Some environments choke on object spread in inline JS. This safely flattens
    patterns like `...{ "zoom":7, "zoomControl":true }` into `"zoom":7, "zoomControl":true`.
    """
    import re
    # Non-greedy match inside braces; multiple occurrences supported
    return re.sub(r"\.\.\.\{([\s\S]*?)\}", r"\1", html)
