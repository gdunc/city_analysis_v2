from __future__ import annotations

from typing import Dict, Iterable, Optional, Any
from pathlib import Path
from urllib.parse import quote_plus

import folium
from folium.plugins import MarkerCluster


def _compute_map_center(records: Iterable[Dict]) -> tuple[float, float]:
    items = list(records)
    if not items:
        # Fallback center over the Alps if no items
        return (46.5, 10.0)
    avg_lat = sum(float(r.get("latitude", 0.0) or 0.0) for r in items) / len(items)
    avg_lon = sum(float(r.get("longitude", 0.0) or 0.0) for r in items) / len(items)
    return (avg_lat, avg_lon)


def _popup_html(r: Dict) -> str:
    name = r.get("name", "Unknown")
    country = r.get("country", "")
    population = r.get("population")
    elevation = r.get("elevation")
    elev_src = r.get("elevation_source")
    # dist_km removed from popup per requirement
    source = r.get("source")
    airport_name = r.get("airport_nearest_name")
    hospital_name = r.get("hospital_nearest_name")
    # Driving times (minutes)
    dta_val = r.get("driving_time_minutes_to_airport")
    dth_val = r.get("driving_time_minutes_to_hospital")
    # Extra fields for filters (embed as hidden data attributes)
    dta = r.get("driving_time_minutes_to_airport", "")
    dth = r.get("driving_time_minutes_to_hospital", "")
    hic = (str(r.get("hospital_in_city") or "").strip().lower())
    hcn = (str(r.get("hospital_in_city_or_nearby") or "").strip().lower())

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
            feet = round(elev_num * 3.28084)
            parts.append(f"<br/>Elevation: {elev_num:.0f} m / {feet:,} ft")
        except Exception:
            parts.append(f"<br/>Elevation: {elevation} m")
    # Add nearest airport name if available
    if airport_name:
        try:
            airport_str = str(airport_name)
            if airport_str.strip():
                parts.append(f"<br/>Nearest airport: {airport_str}")
        except Exception:
            pass
    # Driving time summaries
    try:
        if dta_val not in (None, ""):
            mins = float(dta_val)
            parts.append(f"<br/>Drive to nearest airport: {int(round(mins))} min")
    except Exception:
        pass
    try:
        if dth_val not in (None, ""):
            mins = float(dth_val)
            parts.append(f"<br/>Drive to nearest hospital: {int(round(mins))} min")
    except Exception:
        pass
    # Nearest hospital name
    if hospital_name:
        try:
            hosp_str = str(hospital_name).strip()
            if hosp_str:
                parts.append(f"<br/>Nearest hospital: {hosp_str}")
        except Exception:
            pass
    # Peaks summary
    peaks_count = r.get("peaks_higher1200_within30km_count")
    peaks_names = r.get("peaks_higher1200_within30km_names")
    try:
        if peaks_count not in (None, ""):
            parts.append(f"<br/>Higher peaks within 30 km (≥1200 m): {int(peaks_count)}")
    except Exception:
        pass
    if peaks_names:
        try:
            txt = str(peaks_names)
            if txt.strip():
                # show only first few names to keep popup compact
                short = txt if len(txt) <= 140 else (txt[:137] + "...")
                parts.append(f"<br/>Peaks: {short}")
        except Exception:
            pass

    if source:
        parts.append(f"<br/>Source: {source}")
    if elev_src:
        parts.append(f" <i>({elev_src})</i>")
    # Add Google search link for the city name
    try:
        name_str = str(name).strip()
        if name_str and name_str.lower() != "unknown":
            q = quote_plus(name_str)
            parts.append(f'<br/><a href="https://www.google.com/search?q={q}" target="_blank" rel="noopener noreferrer">Search on Google</a>')
    except Exception:
        pass
    # Hidden metadata carrier for client-side filters
    try:
        parts.append(
            f"<span class=\"city-meta\" style=\"display:none\" "
            f"data-dta=\"{dta}\" data-dth=\"{dth}\" data-hic=\"{hic}\" data-hcn=\"{hcn}\"></span>"
        )
    except Exception:
        pass
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
    # Default to Alps center for better initial view
    center = (46.5, 10.0)  # Alps region
    fmap = folium.Map(location=center, zoom_start=7, tiles=tiles, control_scale=True)

    cluster = MarkerCluster(name="Cities").add_to(fmap)
    peaks_group = folium.FeatureGroup(name="Peaks (≥1200m over city within 30km)").add_to(fmap)
    seen_peak_keys: set[tuple[float, float, str]] = set()

    for r in records_list:
        try:
            lat = float(r["latitude"])  # required
            lon = float(r["longitude"])  # required
        except Exception:
            continue
        popup = folium.Popup(_popup_html(r), max_width=350)
        color = _marker_color(r.get("population"))
        # Attach population as a data attribute for client-side filtering
        # Ensure it is a plain integer to avoid parsing issues in JS
        def _coerce_int(v: Any) -> int:
            try:
                if isinstance(v, str):
                    v = v.replace(",", "").replace(" ", "")
                return int(float(v))
            except Exception:
                return 0
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
            **{
                "population": _coerce_int(r.get("population", 0)),
                # Additional attributes for filtering
                "driving_time_to_airport_minutes": r.get("driving_time_minutes_to_airport", ""),
                "driving_time_to_hospital_minutes": r.get("driving_time_minutes_to_hospital", ""),
                "hospital_in_city": r.get("hospital_in_city", ""),
                "hospital_in_city_or_nearby": r.get("hospital_in_city_or_nearby", ""),
            }
        ).add_to(cluster)

        # Add peak markers if present
        peaks_list = r.get("peaks_higher1200_within30km") or []
        try:
            for pk in peaks_list:
                plat = float(pk.get("latitude"))
                plon = float(pk.get("longitude"))
                pname = str(pk.get("name") or "Peak")
                key = (round(plat, 5), round(plon, 5), pname.strip())
                if key in seen_peak_keys:
                    continue
                pelev = pk.get("elevation")
                if pelev not in (None, ""):
                    try:
                        m_val = float(pelev)
                        ft_val = int(round(m_val * 3.28084))
                        pelev_str = f" ({int(round(m_val))} m / {ft_val:,} ft)"
                    except Exception:
                        pelev_str = f" ({pelev} m)"
                else:
                    pelev_str = ""
                folium.CircleMarker(
                    location=(plat, plon),
                    radius=4,
                    color="black",
                    fill=True,
                    fill_color="white",
                    fill_opacity=0.9,
                    popup=folium.Popup(f"{pname}{pelev_str}", max_width=220),
                ).add_to(peaks_group)
                seen_peak_keys.add(key)
        except Exception:
            pass

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
    # Default to Alps center for better initial view
    center = (46.5, 10.0)  # Alps region
    fmap = folium.Map(location=center, zoom_start=7, tiles=tiles, control_scale=True)

    # Prepare color mapping and population scaling
    countries = [str(r.get("country") or "UNK") for r in items]
    color_map = _country_color_map(countries)
    min_pop, max_pop = _population_bounds(items)

    # Create single peaks group for all peaks
    all_peaks_group = folium.FeatureGroup(name="Peaks (≥1200m over city within 30km)")
    all_peaks_seen_keys: set[tuple[float, float, str]] = set()

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
            def _coerce_int(v: Any) -> int:
                try:
                    if isinstance(v, str):
                        v = v.replace(",", "").replace(" ", "")
                    return int(float(v))
                except Exception:
                    return 0
            folium.CircleMarker(
                location=(lat, lon),
                radius=radius,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                popup=popup,
                tooltip=None,
                **{
                    "population": _coerce_int(r.get("population", 0)),
                    "driving_time_to_airport_minutes": r.get("driving_time_minutes_to_airport", ""),
                    "driving_time_to_hospital_minutes": r.get("driving_time_minutes_to_hospital", ""),
                    "hospital_in_city": r.get("hospital_in_city", ""),
                    "hospital_in_city_or_nearby": r.get("hospital_in_city_or_nearby", ""),
                }
            ).add_to(cluster)
            # Add peaks for this city to the single peaks layer
            peaks_list = r.get("peaks_higher1200_within30km") or []
            try:
                for pk in peaks_list:
                    plat = float(pk.get("latitude"))
                    plon = float(pk.get("longitude"))
                    pname = str(pk.get("name") or "Peak")
                    key = (round(plat, 5), round(plon, 5), pname.strip())
                    if key in all_peaks_seen_keys:
                        continue
                    pelev = pk.get("elevation")
                    if pelev not in (None, ""):
                        try:
                            m_val = float(pelev)
                            ft_val = int(round(m_val * 3.28084))
                            pelev_str = f" ({int(round(m_val))} m / {ft_val:,} ft)"
                        except Exception:
                            pelev_str = f" ({pelev} m)"
                    else:
                        pelev_str = ""
                    folium.CircleMarker(
                        location=(plat, plon),
                        radius=4,
                        color="black",
                        fill=True,
                        fill_color="white",
                        fill_opacity=0.9,
                        popup=folium.Popup(f"{pname}{pelev_str}", max_width=220),
                    ).add_to(all_peaks_group)
                    all_peaks_seen_keys.add(key)
            except Exception:
                pass
        group.add_to(fmap)

    # Add the single peaks group to the map
    all_peaks_group.add_to(fmap)

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
    """Add UI and JS to filter markers by population, driving times, and hospital presence.

    Expects markers to carry options: population, driving_time_to_airport_minutes,
    driving_time_to_hospital_minutes, hospital_in_city, hospital_in_city_or_nearby.
    """
    # HTML control (top-left)
    html = (
        '<div id="pop-filter" style="background: white; padding: 8px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); max-width: 260px;">\n'
        '  <div style="font-size:12px; margin-bottom:6px;"><b>Filters</b></div>\n'
        '  <div style="font-size:12px; margin-bottom:6px;">\n'
        '    <label>Min population</label><br/>\n'
        '    <input id="pop-threshold" type="number" min="0" step="1000" value="0" style="width:120px;"/>\n'
        '  </div>\n'
        '  <div style="font-size:12px; margin-bottom:6px;">\n'
        '    <label>Max driving time to airport (min)</label><br/>\n'
        '    <input id="max-airport-mins" type="number" min="0" step="5" placeholder="" style="width:120px;"/>\n'
        '  </div>\n'
        '  <div style="font-size:12px; margin-bottom:6px;">\n'
        '    <label>Max driving time to hospital (min)</label><br/>\n'
        '    <input id="max-hospital-mins" type="number" min="0" step="5" placeholder="" style="width:120px;"/>\n'
        '  </div>\n'
        '  <div style="font-size:12px; margin-bottom:6px;">\n'
        '    <label>Hospital in city?</label><br/>\n'
        '    <select id="hospital-in-city" style="width:140px;">\n'
        '      <option value="any" selected>any</option>\n'
        '      <option value="yes">yes</option>\n'
        '      <option value="no">no</option>\n'
        '    </select>\n'
        '  </div>\n'
        '  <div style="font-size:12px; margin-bottom:8px;">\n'
        '    <label>Hospital in city or nearby?</label><br/>\n'
        '    <select id="hospital-in-city-or-nearby" style="width:140px;">\n'
        '      <option value="any" selected>any</option>\n'
        '      <option value="yes">yes</option>\n'
        '      <option value="no">no</option>\n'
        '    </select>\n'
        '  </div>\n'
        '  <div>\n'
        '    <button id="apply-pop-filter" style="margin-right:6px;">Apply</button>\n'
        '    <button id="reset-pop-filter">Reset</button>\n'
        '  </div>\n'
        '</div>'
    )

    # No MacroElement: we'll create the control entirely in JS at runtime

    # JS to apply filter (handles MarkerCluster ownership)
    script = r"""
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

      function readMeta(marker){
        try {
          var popup = marker.getPopup && marker.getPopup();
          var content = popup && (popup.getContent && popup.getContent());
          var root;
          if (typeof content === 'string') {
            var div = document.createElement('div');
            div.innerHTML = content;
            root = div;
          } else if (content && content instanceof HTMLElement) {
            root = content;
          } else if (content && content.innerHTML) {
            var d2 = document.createElement('div');
            d2.innerHTML = content.innerHTML;
            root = d2;
          }
          if (!root) return { dta:null, dth:null, hic:'', hcn:'' };
          var meta = root.querySelector('.city-meta');
          if (!meta) return { dta:null, dth:null, hic:'', hcn:'' };
          var dta = meta.getAttribute('data-dta');
          var dth = meta.getAttribute('data-dth');
          var hic = (meta.getAttribute('data-hic') || '').toLowerCase();
          var hcn = (meta.getAttribute('data-hcn') || '').toLowerCase();
          var dtaNum = (dta !== null && dta !== '') ? Number(dta) : null;
          var dthNum = (dth !== null && dth !== '') ? Number(dth) : null;
          if (isNaN(dtaNum)) dtaNum = null;
          if (isNaN(dthNum)) dthNum = null;
          return { dta: dtaNum, dth: dthNum, hic: hic, hcn: hcn };
        } catch (e) {
          return { dta:null, dth:null, hic:'', hcn:'' };
        }
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

      function applyFilter(minPop, maxAirportMins, maxHospitalMins, hospitalInCity, hospitalInCityNearby){
        if (!state.indexBuilt) buildIndex();
        for (var i=0;i<state.markers.length;i++){
          var m = state.markers[i];
          var p = readPopulation(m);
          var show = (p >= minPop);
          var meta = readMeta(m);
          if (show && maxAirportMins != null){
            if (meta.dta == null) { show = false; } else { show = show && (meta.dta <= maxAirportMins); }
          }
          if (show && maxHospitalMins != null){
            if (meta.dth == null) { show = false; } else { show = show && (meta.dth <= maxHospitalMins); }
          }
          if (show && hospitalInCity && hospitalInCity !== 'any'){
            show = show && (meta.hic === hospitalInCity);
          }
          if (show && hospitalInCityNearby && hospitalInCityNearby !== 'any'){
            show = show && (meta.hcn === hospitalInCityNearby);
          }
          if (show) showMarker(m); else hideMarker(m);
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
        var reset = document.getElementById('reset-pop-filter');
        var input = document.getElementById('pop-threshold');
        var maxA = document.getElementById('max-airport-mins');
        var maxH = document.getElementById('max-hospital-mins');
        var hic = document.getElementById('hospital-in-city');
        var hcn = document.getElementById('hospital-in-city-or-nearby');
        if (!btn || !input) return;
        btn.addEventListener('click', function(){
          var v = Number(input.value || 0) || 0;
          var a = (maxA && maxA.value !== '') ? (Number(maxA.value)) : null;
          var h = (maxH && maxH.value !== '') ? (Number(maxH.value)) : null;
          var ic = (hic && hic.value) ? hic.value : 'any';
          var cn = (hcn && hcn.value) ? hcn.value : 'any';
          applyFilter(v, a, h, ic, cn);
        });
        input.addEventListener('keypress', function(e){
          if (e.key === 'Enter') {
            var v = Number(input.value || 0) || 0;
            var a = (maxA && maxA.value !== '') ? (Number(maxA.value)) : null;
            var h = (maxH && maxH.value !== '') ? (Number(maxH.value)) : null;
            var ic = (hic && hic.value) ? hic.value : 'any';
            var cn = (hcn && hcn.value) ? hcn.value : 'any';
            applyFilter(v, a, h, ic, cn);
          }
        });
        if (reset){
          reset.addEventListener('click', function(){
            if (input) input.value = 0;
            if (maxA) maxA.value = '';
            if (maxH) maxH.value = '';
            if (hic) hic.value = 'any';
            if (hcn) hcn.value = 'any';
            applyFilter(0, null, null, 'any', 'any');
          });
        }
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


# --- Optimized map generation with external data ---

def _add_attribution_footer(html: str) -> str:
    """Add attribution footer to HTML for legal compliance."""
    footer = """
    <div style="position: fixed; bottom: 0; left: 0; right: 0; background: rgba(255,255,255,0.95); 
                padding: 8px 15px; font-size: 11px; border-top: 1px solid #ccc; z-index: 9999;
                box-shadow: 0 -2px 4px rgba(0,0,0,0.1);">
        <strong>Data Sources:</strong> 
        City data © <a href="https://www.geonames.org/" target="_blank">GeoNames</a> (CC BY 4.0) | 
        Hospital data © <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a> (ODbL) | 
        Elevation data: SRTM | 
        Airport data: <a href="https://ourairports.com/" target="_blank">OurAirports</a> (Public Domain) | 
        <a href="attribution.html" target="_blank">Full Attribution & Legal</a>
    </div>
    """
    # Insert before closing body tag
    return html.replace("</body>", f"{footer}\n</body>")


def build_optimized_map(data_url: str, tiles: str = "OpenTopoMap", map_title: str = "Mountain Cities") -> folium.Map:
    """Build map that loads data from external JSON file.
    
    Args:
        data_url: URL or path to JSON data file (relative or absolute)
        tiles: Tile provider (default: OpenTopoMap for topographical maps)
        map_title: Title for the map
    """
    # Create base map with OpenTopoMap tiles for topographical features
    center = (46.5, 10.0)  # Alps region default
    
    if tiles == "OpenTopoMap":
        # Use OpenTopoMap tiles explicitly for topographical maps
        fmap = folium.Map(
            location=center,
            zoom_start=5,
            tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
            attr='Map data: © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: © <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)',
            control_scale=True
        )
    else:
        fmap = folium.Map(location=center, zoom_start=5, tiles=tiles, control_scale=True)
    
    # Add a dummy MarkerCluster to ensure the library is loaded
    # The JavaScript will handle actual marker creation
    MarkerCluster(name="Loading...").add_to(fmap)
    
    # Add script to load data and render markers
    script = """
    <script>
    (function(){
        var dataUrl = '%DATA_URL%';
        var mapVar = '%MAP%';
        
        function getMap(){ return window[mapVar]; }
        
        // Check if we're running in file:// protocol (local file)
        if (window.location.protocol === 'file:') {
            alert('This map requires a web server to load data. Please serve these files through a local web server (e.g., python -m http.server) or upload to a web hosting service.');
            return;
        }

        fetch(dataUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                console.log('Loaded ' + data.length + ' cities');
                renderMarkers(data);
            })
            .catch(error => {
                console.error('Error loading data:', error);
                var errorMsg = 'Error loading map data. ';

                if (window.location.protocol === 'file:') {
                    errorMsg += 'This map must be served through a web server. Please use: python -m http.server 8000 (or similar) in the directory containing this file.';
                } else {
                    errorMsg += 'Please check your internet connection and refresh the page.';
                }

                alert(errorMsg);
            });
        
        function renderMarkers(records) {
            var map = getMap();
            if (!map) {
                console.error('Map not ready');
                return;
            }
            
            // Create marker cluster
            var cluster = L.markerClusterGroup();
            
            // Create peaks layer
            var peaksGroup = L.featureGroup();
            var seenPeaks = {};
            
            records.forEach(function(r) {
                if (!r.latitude || !r.longitude) return;
                
                var lat = parseFloat(r.latitude);
                var lon = parseFloat(r.longitude);
                
                // Build popup
                var popup = buildPopup(r);
                
                // Determine color based on population
                var color = getMarkerColor(r.population);
                
                // Create marker
                var marker = L.circleMarker([lat, lon], {
                    radius: 6,
                    color: color,
                    fillColor: color,
                    fillOpacity: 0.85,
                    population: parseInt(r.population) || 0,
                    driving_time_to_airport_minutes: r.driving_time_minutes_to_airport || '',
                    driving_time_to_hospital_minutes: r.driving_time_minutes_to_hospital || '',
                    hospital_in_city: r.hospital_in_city || '',
                    hospital_in_city_or_nearby: r.hospital_in_city_or_nearby || ''
                }).bindPopup(popup, {maxWidth: 350});
                
                cluster.addLayer(marker);
                
                // Add peaks if present
                if (r.peaks_higher1200_within30km && Array.isArray(r.peaks_higher1200_within30km)) {
                    r.peaks_higher1200_within30km.forEach(function(pk) {
                        var plat = parseFloat(pk.latitude);
                        var plon = parseFloat(pk.longitude);
                        var pname = pk.name || 'Peak';
                        var key = plat.toFixed(5) + ',' + plon.toFixed(5) + ',' + pname;
                        
                        if (seenPeaks[key]) return;
                        seenPeaks[key] = true;
                        
                        var elevStr = '';
                        if (pk.elevation) {
                            var m = parseFloat(pk.elevation);
                            var ft = Math.round(m * 3.28084);
                            elevStr = ' (' + Math.round(m) + ' m / ' + ft.toLocaleString() + ' ft)';
                        }
                        
                        L.circleMarker([plat, plon], {
                            radius: 4,
                            color: 'black',
                            fillColor: 'white',
                            fillOpacity: 0.9
                        }).bindPopup(pname + elevStr, {maxWidth: 220})
                          .addTo(peaksGroup);
                    });
                }
            });
            
            map.addLayer(cluster);
            peaksGroup.addTo(map);
            
            // Add layer control
            var overlays = {
                'Cities': cluster,
                'Peaks (≥1200m over city within 30km)': peaksGroup
            };
            L.control.layers(null, overlays, {collapsed: false}).addTo(map);
            
            // Fit bounds to data
            if (cluster.getLayers().length > 0) {
                map.fitBounds(cluster.getBounds(), {padding: [50, 50]});
            }
        }
        
        function getMarkerColor(population) {
            var pop = parseFloat(population) || 0;
            if (pop >= 100000) return 'darkred';
            if (pop >= 50000) return 'red';
            if (pop >= 20000) return 'orange';
            if (pop >= 10000) return 'green';
            return 'blue';
        }
        
        function buildPopup(r) {
            var parts = [];
            parts.push('<b>' + (r.name || 'Unknown') + '</b>');
            if (r.country) parts.push(' (' + r.country + ')');
            
            if (r.population) {
                parts.push('<br/>Population: ' + parseInt(r.population).toLocaleString());
            }
            
            if (r.elevation) {
                var m = parseFloat(r.elevation);
                var ft = Math.round(m * 3.28084);
                parts.push('<br/>Elevation: ' + Math.round(m) + ' m / ' + ft.toLocaleString() + ' ft');
            }
            
            if (r.airport_nearest_name) {
                parts.push('<br/>Nearest airport: ' + r.airport_nearest_name);
            }
            
            if (r.driving_time_minutes_to_airport) {
                parts.push('<br/>Drive to nearest airport: ' + Math.round(r.driving_time_minutes_to_airport) + ' min');
            }
            
            if (r.driving_time_minutes_to_hospital) {
                parts.push('<br/>Drive to nearest hospital: ' + Math.round(r.driving_time_minutes_to_hospital) + ' min');
            }
            
            if (r.hospital_nearest_name) {
                parts.push('<br/>Nearest hospital: ' + r.hospital_nearest_name);
            }
            
            if (r.peaks_higher1200_within30km_count) {
                parts.push('<br/>Higher peaks within 30 km (≥1200 m): ' + r.peaks_higher1200_within30km_count);
            }
            
            if (r.peaks_higher1200_within30km_names) {
                var names = r.peaks_higher1200_within30km_names;
                if (names.length > 140) names = names.substring(0, 137) + '...';
                parts.push('<br/>Peaks: ' + names);
            }
            
            if (r.source) {
                parts.push('<br/>Source: ' + r.source);
            }
            
            if (r.name && r.name.toLowerCase() !== 'unknown') {
                var q = encodeURIComponent(r.name);
                parts.push('<br/><a href="https://www.google.com/search?q=' + q + '" target="_blank" rel="noopener noreferrer">Search on Google</a>');
            }
            
            // Hidden metadata for filters
            parts.push('<span class="city-meta" style="display:none" ' +
                      'data-dta="' + (r.driving_time_minutes_to_airport || '') + '" ' +
                      'data-dth="' + (r.driving_time_minutes_to_hospital || '') + '" ' +
                      'data-hic="' + (r.hospital_in_city || '').toLowerCase() + '" ' +
                      'data-hcn="' + (r.hospital_in_city_or_nearby || '').toLowerCase() + '"></span>');
            
            return parts.join('');
        }
    })();
    </script>
    """
    
    from folium import Element
    script = script.replace("%DATA_URL%", data_url).replace("%MAP%", fmap.get_name())
    fmap.get_root().html.add_child(Element(script))
    
    # Add population filter
    _inject_population_filter(fmap)
    
    return fmap


def save_optimized_map(records: Iterable[Dict], out_path: str | Path, 
                       tiles: str = "OpenTopoMap", map_title: str = "Mountain Cities") -> tuple[Path, Path]:
    """Save map with data in separate JSON file for optimization.
    
    Returns:
        Tuple of (html_path, json_path)
    """
    import json
    
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save data as JSON
    records_list = list(records)
    json_path = out_path.with_suffix('.data.json')
    
    # Clean records for JSON serialization
    clean_records = []
    for r in records_list:
        clean_r = {}
        for k, v in r.items():
            # Skip None values and empty lists
            if v is None or (isinstance(v, list) and len(v) == 0):
                continue
            clean_r[k] = v
        clean_records.append(clean_r)
    
    json_path.write_text(json.dumps(clean_records, indent=2), encoding='utf-8')
    
    # Build map pointing to JSON file
    data_url = json_path.name  # relative path
    fmap = build_optimized_map(data_url, tiles=tiles, map_title=map_title)
    
    html = fmap.get_root().render()
    html = _strip_object_spread_in_html(html)
    html = _add_attribution_footer(html)
    
    out_path.write_text(html, encoding='utf-8')
    
    return out_path, json_path


def save_optimized_country_map(records: Iterable[Dict], out_path: str | Path,
                               tiles: str = "OpenTopoMap", map_title: str = "Mountain Cities") -> tuple[Path, Path]:
    """Save country-colored map with data in separate JSON file.
    
    Returns:
        Tuple of (html_path, json_path)
    """
    import json
    
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save data as JSON
    records_list = list(records)
    json_path = out_path.with_suffix('.data.json')
    
    # Clean records for JSON serialization
    clean_records = []
    for r in records_list:
        clean_r = {}
        for k, v in r.items():
            if v is None or (isinstance(v, list) and len(v) == 0):
                continue
            clean_r[k] = v
        clean_records.append(clean_r)
    
    json_path.write_text(json.dumps(clean_records, indent=2), encoding='utf-8')
    
    # Build optimized country map
    fmap = _build_optimized_country_map(json_path.name, tiles, map_title, records_list)
    
    html = fmap.get_root().render()
    html = _strip_object_spread_in_html(html)
    html = _add_attribution_footer(html)
    
    out_path.write_text(html, encoding='utf-8')
    
    return out_path, json_path


def save_wordpress_map(records: Iterable[Dict], out_path: str | Path, 
                      tiles: str = "OpenTopoMap", map_title: str = "Mountain Cities") -> Path:
    """Save WordPress-compatible single-file map with embedded data.
    
    This creates a single HTML file with all data embedded, perfect for WordPress upload.
    No external JSON files required.
    
    Returns:
        Path to the HTML file
    """
    import json
    
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Clean records for JSON serialization
    records_list = list(records)
    clean_records = []
    for r in records_list:
        clean_r = {}
        for k, v in r.items():
            if v is None or (isinstance(v, list) and len(v) == 0):
                continue
            clean_r[k] = v
        clean_records.append(clean_r)
    
    # Build map with embedded data
    fmap = _build_wordpress_map(clean_records, tiles, map_title)
    
    html = fmap.get_root().render()
    html = _strip_object_spread_in_html(html)
    html = _add_attribution_footer(html)
    
    out_path.write_text(html, encoding='utf-8')
    
    return out_path


def save_wordpress_country_map(records: Iterable[Dict], out_path: str | Path,
                               tiles: str = "OpenTopoMap", map_title: str = "Mountain Cities") -> Path:
    """Save WordPress-compatible country map with embedded data.
    
    This creates a single HTML file with all data embedded, perfect for WordPress upload.
    No external JSON files required.
    
    Returns:
        Path to the HTML file
    """
    import json
    
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Clean records for JSON serialization
    records_list = list(records)
    clean_records = []
    for r in records_list:
        clean_r = {}
        for k, v in r.items():
            if v is None or (isinstance(v, list) and len(v) == 0):
                continue
            clean_r[k] = v
        clean_records.append(clean_r)
    
    # Build country map with embedded data
    fmap = _build_wordpress_country_map(clean_records, tiles, map_title)
    
    html = fmap.get_root().render()
    html = _strip_object_spread_in_html(html)
    html = _add_attribution_footer(html)
    
    out_path.write_text(html, encoding='utf-8')
    
    return out_path


def _build_optimized_country_map(data_url: str, tiles: str, map_title: str, sample_records: list) -> folium.Map:
    """Build country-colored map that loads data externally."""
    center = (46.5, 10.0)
    
    if tiles == "OpenTopoMap":
        # Use OpenTopoMap tiles explicitly for topographical maps
        fmap = folium.Map(
            location=center,
            zoom_start=5,
            tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
            attr='Map data: © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: © <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)',
            control_scale=True
        )
    else:
        fmap = folium.Map(location=center, zoom_start=5, tiles=tiles, control_scale=True)
    
    # Add a dummy MarkerCluster to ensure the library is loaded
    MarkerCluster(name="Loading...").add_to(fmap)
    
    # Pre-compute color mapping from sample
    countries = [str(r.get("country") or "UNK") for r in sample_records]
    color_map = _country_color_map(countries)
    min_pop, max_pop = _population_bounds(sample_records)
    
    script = """
    <script>
    (function(){
        var dataUrl = '%DATA_URL%';
        var mapVar = '%MAP%';
        var colorMap = %COLOR_MAP%;
        var minPop = %MIN_POP%;
        var maxPop = %MAX_POP%;
        
        function getMap(){ return window[mapVar]; }
        
        // Check if we're running in file:// protocol (local file)
        if (window.location.protocol === 'file:') {
            alert('This map requires a web server to load data. Please serve these files through a local web server (e.g., python -m http.server) or upload to a web hosting service.');
            return;
        }

        fetch(dataUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                console.log('Loaded ' + data.length + ' cities');
                renderMarkers(data);
            })
            .catch(error => {
                console.error('Error loading data:', error);
                var errorMsg = 'Error loading map data. ';

                if (window.location.protocol === 'file:') {
                    errorMsg += 'This map must be served through a web server. Please use: python -m http.server 8000 (or similar) in the directory containing this file.';
                } else {
                    errorMsg += 'Please check your internet connection and refresh the page.';
                }

                alert(errorMsg);
            });
        
        function getScaledRadius(pop) {
            var p = parseFloat(pop) || 0;
            if (p <= 0) return 3;
            if (maxPop <= minPop) return 8.5;
            var lp = Math.log10(Math.max(p, 1));
            var lmin = Math.log10(Math.max(minPop, 1));
            var lmax = Math.log10(Math.max(maxPop, 1));
            var t = lmax > lmin ? (lp - lmin) / (lmax - lmin) : 0.5;
            return 3 + t * 11;
        }
        
        function renderMarkers(records) {
            var map = getMap();
            if (!map) {
                console.error('Map not ready');
                return;
            }
            
            // Group by country
            var byCountry = {};
            records.forEach(function(r) {
                var country = r.country || 'UNK';
                if (!byCountry[country]) byCountry[country] = [];
                byCountry[country].push(r);
            });
            
            // Create peaks layer
            var peaksGroup = L.featureGroup();
            var seenPeaks = {};
            
            var allGroups = {};
            
            // Create layer for each country
            Object.keys(byCountry).sort().forEach(function(country) {
                var recs = byCountry[country];
                var group = L.featureGroup();
                var cluster = L.markerClusterGroup();
                var color = colorMap[country] || 'blue';
                
                recs.forEach(function(r) {
                    if (!r.latitude || !r.longitude) return;
                    
                    var lat = parseFloat(r.latitude);
                    var lon = parseFloat(r.longitude);
                    var radius = getScaledRadius(r.population);
                    var popup = buildPopup(r);
                    
                    var marker = L.circleMarker([lat, lon], {
                        radius: radius,
                        color: color,
                        fillColor: color,
                        fillOpacity: 0.85,
                        population: parseInt(r.population) || 0,
                        driving_time_to_airport_minutes: r.driving_time_minutes_to_airport || '',
                        driving_time_to_hospital_minutes: r.driving_time_minutes_to_hospital || '',
                        hospital_in_city: r.hospital_in_city || '',
                        hospital_in_city_or_nearby: r.hospital_in_city_or_nearby || ''
                    }).bindPopup(popup, {maxWidth: 350});
                    
                    cluster.addLayer(marker);
                    
                    // Add peaks
                    if (r.peaks_higher1200_within30km && Array.isArray(r.peaks_higher1200_within30km)) {
                        r.peaks_higher1200_within30km.forEach(function(pk) {
                            var plat = parseFloat(pk.latitude);
                            var plon = parseFloat(pk.longitude);
                            var pname = pk.name || 'Peak';
                            var key = plat.toFixed(5) + ',' + plon.toFixed(5) + ',' + pname;
                            
                            if (seenPeaks[key]) return;
                            seenPeaks[key] = true;
                            
                            var elevStr = '';
                            if (pk.elevation) {
                                var m = parseFloat(pk.elevation);
                                var ft = Math.round(m * 3.28084);
                                elevStr = ' (' + Math.round(m) + ' m / ' + ft.toLocaleString() + ' ft)';
                            }
                            
                            L.circleMarker([plat, plon], {
                                radius: 4,
                                color: 'black',
                                fillColor: 'white',
                                fillOpacity: 0.9
                            }).bindPopup(pname + elevStr, {maxWidth: 220})
                              .addTo(peaksGroup);
                        });
                    }
                });
                
                group.addLayer(cluster);
                group.addTo(map);
                allGroups[country + ' (' + recs.length + ')'] = group;
            });
            
            peaksGroup.addTo(map);
            allGroups['Peaks (≥1200m over city within 30km)'] = peaksGroup;
            
            // Add layer control
            L.control.layers(null, allGroups, {collapsed: false}).addTo(map);
            
            // Fit to all markers
            var allBounds = L.latLngBounds([]);
            Object.values(byCountry).forEach(function(recs) {
                recs.forEach(function(r) {
                    if (r.latitude && r.longitude) {
                        allBounds.extend([parseFloat(r.latitude), parseFloat(r.longitude)]);
                    }
                });
            });
            if (allBounds.isValid()) {
                map.fitBounds(allBounds, {padding: [50, 50]});
            }
        }
        
        function buildPopup(r) {
            var parts = [];
            parts.push('<b>' + (r.name || 'Unknown') + '</b>');
            if (r.country) parts.push(' (' + r.country + ')');
            
            if (r.population) {
                parts.push('<br/>Population: ' + parseInt(r.population).toLocaleString());
            }
            
            if (r.elevation) {
                var m = parseFloat(r.elevation);
                var ft = Math.round(m * 3.28084);
                parts.push('<br/>Elevation: ' + Math.round(m) + ' m / ' + ft.toLocaleString() + ' ft');
            }
            
            if (r.airport_nearest_name) {
                parts.push('<br/>Nearest airport: ' + r.airport_nearest_name);
            }
            
            if (r.driving_time_minutes_to_airport) {
                parts.push('<br/>Drive to nearest airport: ' + Math.round(r.driving_time_minutes_to_airport) + ' min');
            }
            
            if (r.driving_time_minutes_to_hospital) {
                parts.push('<br/>Drive to nearest hospital: ' + Math.round(r.driving_time_minutes_to_hospital) + ' min');
            }
            
            if (r.hospital_nearest_name) {
                parts.push('<br/>Nearest hospital: ' + r.hospital_nearest_name);
            }
            
            if (r.peaks_higher1200_within30km_count) {
                parts.push('<br/>Higher peaks within 30 km (≥1200 m): ' + r.peaks_higher1200_within30km_count);
            }
            
            if (r.peaks_higher1200_within30km_names) {
                var names = r.peaks_higher1200_within30km_names;
                if (names.length > 140) names = names.substring(0, 137) + '...';
                parts.push('<br/>Peaks: ' + names);
            }
            
            if (r.source) {
                parts.push('<br/>Source: ' + r.source);
            }
            
            if (r.name && r.name.toLowerCase() !== 'unknown') {
                var q = encodeURIComponent(r.name);
                parts.push('<br/><a href="https://www.google.com/search?q=' + q + '" target="_blank" rel="noopener noreferrer">Search on Google</a>');
            }
            
            // Hidden metadata for filters
            parts.push('<span class="city-meta" style="display:none" ' +
                      'data-dta="' + (r.driving_time_minutes_to_airport || '') + '" ' +
                      'data-dth="' + (r.driving_time_minutes_to_hospital || '') + '" ' +
                      'data-hic="' + (r.hospital_in_city || '').toLowerCase() + '" ' +
                      'data-hcn="' + (r.hospital_in_city_or_nearby || '').toLowerCase() + '"></span>');
            
            return parts.join('');
        }
    })();
    </script>
    """
    
    import json
    from folium import Element
    script = (script.replace("%DATA_URL%", data_url)
                    .replace("%MAP%", fmap.get_name())
                    .replace("%COLOR_MAP%", json.dumps(color_map))
                    .replace("%MIN_POP%", str(min_pop))
                    .replace("%MAX_POP%", str(max_pop)))
    fmap.get_root().html.add_child(Element(script))
    
    _inject_population_filter(fmap)
    
    return fmap
