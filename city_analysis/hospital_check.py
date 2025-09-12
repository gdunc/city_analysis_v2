from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from openai import OpenAI
from tqdm import tqdm
from math import radians, sin, cos, asin, sqrt
from .geometry import default_alps_polygon, polygon_bounds
from .airport_check import _osrm_route, DriveResult
from .overpass import fetch_overpass_hospitals_bbox_tiled


@dataclass
class HospitalCheckResult:
    hospital_in_city: Optional[str]  # "yes" | "no" | None
    hospital_confidence_pct: Optional[int]
    hospital_reasoning: Optional[str]
    hospital_error: Optional[str]


def _extract_first_json(text: str) -> Optional[Dict]:
    """Best-effort extraction of the first JSON object from a text blob."""
    if not text:
        return None
    # Try fenced JSON first
    fenced = re.findall(r"```json\s*(\{[\s\S]*?\})\s*```", text)
    candidates: List[str] = []
    if fenced:
        candidates.extend(fenced)
    # Fallback: first top-level {...}
    braces = re.findall(r"\{[\s\S]*\}", text)
    if braces:
        candidates.append(braces[0])
    for cand in candidates:
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def _coerce_result(payload: Dict) -> HospitalCheckResult:
    def norm_yes_no(val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        v = str(val).strip().lower()
        if v in {"yes", "no"}:
            return v
        return None

    hospital_in_city = norm_yes_no(payload.get("hospital_in_city"))
    # Accept either integer or float; clamp to [0,100]
    conf_raw = payload.get("confidence_pct") or payload.get("hospital_confidence_pct")
    confidence: Optional[int] = None
    if conf_raw is not None:
        try:
            confidence = int(round(float(conf_raw)))
            confidence = max(0, min(100, confidence))
        except Exception:
            confidence = None

    # Reasoning and sources
    reasoning = payload.get("reasoning") or payload.get("hospital_reasoning")
    sources = payload.get("sources") or payload.get("urls") or []
    if isinstance(sources, list) and sources:
        # Append up to 3 URLs into the reasoning for convenience
        links = ", ".join([str(u) for u in sources[:3]])
        if reasoning:
            reasoning = f"{reasoning} | Sources: {links}"
        else:
            reasoning = f"Sources: {links}"

    return HospitalCheckResult(
        hospital_in_city=hospital_in_city,
        hospital_confidence_pct=confidence,
        hospital_reasoning=reasoning,
        hospital_error=None,
    )


def _build_prompt(city: str, country: str) -> str:
    return (
        "You are a rigorous web research assistant. Use the web_search tool to search the web, "
        "then answer strictly based on reputable sources (official hospital/health system sites, "
        "government or public health portals, national healthcare directories, or Wikipedia only if it cites official sources).\n\n"
        f"Question: Is there at least one hospital located within the city limits of {city}, {country}?\n"
        "- If unsure because sources conflict or are unclear, answer 'no' with lower confidence.\n"
        "- Provide 1-2 sentence reasoning and include 1-3 relevant URLs.\n\n"
        "Return JSON ONLY with this exact schema and field names:\n"
        "{\n"
        "  \"hospital_in_city\": \"yes\" | \"no\",\n"
        "  \"confidence_pct\": number (0-100),\n"
        "  \"reasoning\": string,\n"
        "  \"sources\": [string URL, ...]\n"
        "}"
    )


def _query_openai_with_web_search(client: OpenAI, model: str, city: str, country: str, request_timeout: Optional[float] = 60.0) -> HospitalCheckResult:
    try:
        prompt = _build_prompt(city, country)
        # Use Responses API with web_search tool. Fallbacks are handled below.
        response = client.responses.create(
            model=model,
            input=(
                "System: Follow instructions exactly. Do not fabricate sources. Return ONLY JSON.\n\n" + prompt
            ),
            tools=[{"type": "web_search"}],
            timeout=request_timeout,
        )

        # Try structured content first (json_schema response)
        try:
            for item in getattr(response, "output", []) or []:
                for content in getattr(item, "content", []) or []:
                    if getattr(content, "type", None) == "output_json" and getattr(content, "output", None):
                        return _coerce_result(content.output)
        except Exception:
            pass

        # Fallback: parse text output as JSON
        text: Optional[str] = None
        try:
            # SDK often exposes a convenience field
            text = getattr(response, "output_text", None)
        except Exception:
            text = None

        if not text:
            # Try to gather from content blocks
            try:
                chunks: List[str] = []
                for item in getattr(response, "output", []) or []:
                    for content in getattr(item, "content", []) or []:
                        if getattr(content, "type", None) == "output_text" and getattr(content, "text", None):
                            chunks.append(content.text)
                text = "\n".join(chunks) if chunks else None
            except Exception:
                text = None

        if not text:
            return HospitalCheckResult(
                hospital_in_city=None,
                hospital_confidence_pct=None,
                hospital_reasoning=None,
                hospital_error="OpenAI returned no output",
            )

        parsed = _extract_first_json(text)
        if not parsed:
            return HospitalCheckResult(
                hospital_in_city=None,
                hospital_confidence_pct=None,
                hospital_reasoning=text[:5000],
                hospital_error="Failed to parse JSON from model output",
            )

        return _coerce_result(parsed)

    except Exception as e:
        return HospitalCheckResult(
            hospital_in_city=None,
            hospital_confidence_pct=None,
            hospital_reasoning=None,
            hospital_error=str(e),
        )


def enrich_records_with_hospital_presence(
    records: Iterable[Dict],
    model: str = "gpt-5",
    request_timeout: Optional[float] = 60.0,
    sleep_seconds_between_requests: float = 0.5,
) -> List[Dict]:
    """
    For each record, query OpenAI with web search to determine if the city has at least one hospital.
    Returns a new list of records with additional columns:
      - hospital_in_city: "yes" | "no" (blank if error)
      - hospital_confidence_pct: integer 0-100 (blank if error)
      - hospital_reasoning: brief reasoning with links (blank if error)
      - hospital_error: error message if any API/parsing error
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    enriched: List[Dict] = []

    for r in tqdm(list(records), desc="Checking hospitals", unit="city"):
        city = str(r.get("name") or r.get("city") or "").strip()
        country = str(r.get("country") or "").strip()

        result = _query_openai_with_web_search(
            client=client,
            model=model,
            city=city,
            country=country,
            request_timeout=request_timeout,
        )

        new_record = dict(r)
        if result.hospital_error:
            new_record["hospital_in_city"] = ""
            new_record["hospital_confidence_pct"] = ""
            new_record["hospital_reasoning"] = ""
            new_record["hospital_error"] = result.hospital_error
        else:
            new_record["hospital_in_city"] = result.hospital_in_city or ""
            new_record["hospital_confidence_pct"] = (
                result.hospital_confidence_pct if result.hospital_confidence_pct is not None else ""
            )
            new_record["hospital_reasoning"] = result.hospital_reasoning or ""
            new_record["hospital_error"] = ""

        enriched.append(new_record)

        # Gentle pacing to avoid hammering the API
        if sleep_seconds_between_requests > 0:
            time.sleep(sleep_seconds_between_requests)

    return enriched



# ----------------- OSM-based hospital presence check -----------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points using Haversine (km)."""
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371.0
    return r * c


def _load_hospitals_for_bbox(bbox: Tuple[float, float, float, float], tile_size_deg: float = 1.0, sleep_between: float = 0.5) -> List[Dict]:
    """Fetch hospitals from Overpass within bbox using tiling, return normalized list.

    Returns list of dicts with keys: name, latitude, longitude, source, _tags
    """
    hospitals = fetch_overpass_hospitals_bbox_tiled(
        bbox=bbox,
        tile_size_deg=tile_size_deg,
        sleep_between=sleep_between,
    )
    return hospitals


def enrich_records_with_hospital_presence_osm(
    records: Iterable[Dict],
    perimeter_bbox: Optional[Tuple[float, float, float, float]] = None,
    radius_km: float = 3.0,
    tile_size_deg: float = 1.0,
    sleep_between_tiles: float = 0.5,
    fallback_to_openai: bool = False,
    model: str = "gpt-5",
    request_timeout: Optional[float] = 60.0,
    sleep_seconds_between_requests: float = 0.5,
    osrm_base_url: str = "https://router.project-osrm.org",
) -> List[Dict]:
    """Determine hospital presence using OSM hospitals within a radius around city centroid.

    - If any OSM hospital lies within radius_km of a city's (lat,lon), mark yes; else no.
    - If fallback_to_openai is True, call the OpenAI web search method only for cities
      where OSM found none, to potentially flip "no" to "yes" with reasoning.
    """
    # Determine bbox to query for hospitals
    if perimeter_bbox is None:
        perimeter_bbox = polygon_bounds(default_alps_polygon())

    # Fetch hospitals once
    hospitals = _load_hospitals_for_bbox(perimeter_bbox, tile_size_deg=tile_size_deg, sleep_between=sleep_between_tiles)

    # Precompute for quick coarse filter
    deg_radius = max(0.001, radius_km / 111.0)  # ~1 deg ~111 km

    enriched: List[Dict] = []
    client: Optional[OpenAI] = None
    if fallback_to_openai:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    for r in tqdm(list(records), desc="Checking hospitals (OSM)", unit="city"):
        city = str(r.get("name") or r.get("city") or "").strip()
        country = str(r.get("country") or "").strip()
        try:
            lat0 = float(r.get("latitude"))
            lon0 = float(r.get("longitude"))
        except Exception:
            lat0, lon0 = None, None

        found = False
        nearest_km: Optional[float] = None
        nearest_hospital: Optional[Dict] = None
        if lat0 is not None and lon0 is not None:
            # First pass: coarse scan within a small degree window for quick positives
            for h in hospitals:
                hlat = float(h.get("latitude"))
                hlon = float(h.get("longitude"))
                if abs(hlat - lat0) > deg_radius or abs(hlon - lon0) > deg_radius:
                    continue
                d = _haversine_km(lat0, lon0, hlat, hlon)
                if nearest_km is None or d < nearest_km:
                    nearest_km = d
                    nearest_hospital = h
                if d <= radius_km:
                    found = True
                    break
            # Second pass: if nothing nearby, compute true nearest across all hospitals
            if nearest_km is None:
                for h in hospitals:
                    hlat = float(h.get("latitude"))
                    hlon = float(h.get("longitude"))
                    d = _haversine_km(lat0, lon0, hlat, hlon)
                    if nearest_km is None or d < nearest_km:
                        nearest_km = d
                        nearest_hospital = h

        new_record = dict(r)
        # Primary presence determination
        if found:
            new_record["hospital_in_city"] = "yes"
            new_record["hospital_confidence_pct"] = 95
            reason = f"OSM hospital within {radius_km:.1f} km of centroid"
            if nearest_km is not None:
                reason += f" (nearest {nearest_km:.2f} km)"
            new_record["hospital_reasoning"] = reason
            new_record["hospital_error"] = ""
        else:
            # Not found within radius; optionally ask OpenAI for presence only
            if fallback_to_openai and client is not None:
                result = _query_openai_with_web_search(
                    client=client,
                    model=model,
                    city=city,
                    country=country,
                    request_timeout=request_timeout,
                )
                if sleep_seconds_between_requests > 0:
                    time.sleep(sleep_seconds_between_requests)
                if result.hospital_error:
                    new_record["hospital_in_city"] = ""
                    new_record["hospital_confidence_pct"] = ""
                    new_record["hospital_reasoning"] = ""
                    new_record["hospital_error"] = result.hospital_error
                else:
                    new_record["hospital_in_city"] = result.hospital_in_city or ""
                    new_record["hospital_confidence_pct"] = (
                        result.hospital_confidence_pct if result.hospital_confidence_pct is not None else ""
                    )
                    new_record["hospital_reasoning"] = result.hospital_reasoning or ""
                    new_record["hospital_error"] = ""
            else:
                # No fallback; mark confidently based on OSM absence (within radius)
                new_record["hospital_in_city"] = "no"
                new_record["hospital_confidence_pct"] = 80
                if nearest_km is not None:
                    new_record["hospital_reasoning"] = (
                        f"No OSM hospital within {radius_km:.1f} km of centroid; nearest {nearest_km:.2f} km"
                    )
                else:
                    new_record["hospital_reasoning"] = f"No OSM hospital within {radius_km:.1f} km of centroid"
                new_record["hospital_error"] = ""

        # Populate nearest hospital info if available
        if nearest_km is not None:
            try:
                new_record["nearest_hospital_km"] = round(float(nearest_km), 2)
            except Exception:
                new_record["nearest_hospital_km"] = nearest_km
        try:
            nh = float(new_record.get("nearest_hospital_km", nearest_km if nearest_km is not None else 1e9))
            new_record["hospital_in_city_or_nearby"] = "yes" if nh <= 25.0 else "no"
        except Exception:
            new_record["hospital_in_city_or_nearby"] = ""

        if nearest_hospital is not None:
            name_val = str(nearest_hospital.get("name") or "").strip()
            try:
                hlat_val = float(nearest_hospital.get("latitude"))
            except Exception:
                hlat_val = None
            try:
                hlon_val = float(nearest_hospital.get("longitude"))
            except Exception:
                hlon_val = None
            new_record["hospital_nearest_name"] = name_val
            new_record["hospital_nearest_latitude"] = hlat_val if hlat_val is not None else ""
            new_record["hospital_nearest_longitude"] = hlon_val if hlon_val is not None else ""
        else:
            new_record["hospital_nearest_name"] = ""
            new_record["hospital_nearest_latitude"] = ""
            new_record["hospital_nearest_longitude"] = ""

        # Driving distance/time via OSRM to nearest hospital when coordinates are available
        if (
            isinstance(lat0, (int, float))
            and isinstance(lon0, (int, float))
            and isinstance(new_record.get("hospital_nearest_latitude"), (int, float))
            and isinstance(new_record.get("hospital_nearest_longitude"), (int, float))
        ):
            drive: DriveResult = _osrm_route(
                city_lat=float(lat0),
                city_lon=float(lon0),
                airport_lat=float(new_record["hospital_nearest_latitude"]),
                airport_lon=float(new_record["hospital_nearest_longitude"]),
                base_url=osrm_base_url,
                request_timeout=30.0,
            )
            if drive.driving_error:
                new_record["driving_km_to_hospital"] = ""
                new_record["driving_time_minutes_to_hospital"] = ""
            else:
                new_record["driving_km_to_hospital"] = (
                    drive.driving_km_to_airport if drive.driving_km_to_airport is not None else ""
                )
                new_record["driving_time_minutes_to_hospital"] = (
                    drive.driving_time_minutes_to_airport if drive.driving_time_minutes_to_airport is not None else ""
                )
        else:
            new_record["driving_km_to_hospital"] = ""
            new_record["driving_time_minutes_to_hospital"] = ""

        enriched.append(new_record)

    return enriched

