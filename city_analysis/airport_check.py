from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from openai import OpenAI
from tqdm import tqdm
import random


@dataclass
class AirportResult:
    airport_name: Optional[str]
    airport_iata: Optional[str]
    airport_icao: Optional[str]
    airport_latitude: Optional[float]
    airport_longitude: Optional[float]
    airport_confidence_pct: Optional[int]
    airport_reasoning: Optional[str]
    airport_error: Optional[str]


@dataclass
class DriveResult:
    driving_km_to_airport: Optional[float]
    driving_time_minutes_to_airport: Optional[float]
    driving_confidence_pct: Optional[int]
    driving_reasoning: Optional[str]
    driving_error: Optional[str]


def _extract_first_json(text: str) -> Optional[Dict]:
    if not text:
        return None
    fenced = re.findall(r"```json\s*(\{[\s\S]*?\})\s*```", text)
    candidates: List[str] = []
    if fenced:
        candidates.extend(fenced)
    braces = re.findall(r"\{[\s\S]*\}", text)
    if braces:
        candidates.append(braces[0])
    for cand in candidates:
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def _coerce_airport_result(payload: Dict) -> AirportResult:
    def to_int_pct(val: Optional[object]) -> Optional[int]:
        if val is None:
            return None
        try:
            pct = int(round(float(val)))
            return max(0, min(100, pct))
        except Exception:
            return None

    # Reasoning and sources
    reasoning = payload.get("reasoning")
    sources = payload.get("sources") or payload.get("urls") or []
    if isinstance(sources, list) and sources:
        links = ", ".join([str(u) for u in sources[:5]])
        if reasoning:
            reasoning = f"{reasoning} | Sources: {links}"
        else:
            reasoning = f"Sources: {links}"

    lat = None
    lon = None
    try:
        lat_val = payload.get("airport_latitude") or payload.get("lat")
        lon_val = payload.get("airport_longitude") or payload.get("lon") or payload.get("lng")
        lat = float(lat_val) if lat_val is not None else None
        lon = float(lon_val) if lon_val is not None else None
    except Exception:
        lat = None
        lon = None

    return AirportResult(
        airport_name=(payload.get("airport_name") or payload.get("name") or None),
        airport_iata=(payload.get("airport_iata") or payload.get("iata") or None),
        airport_icao=(payload.get("airport_icao") or payload.get("icao") or None),
        airport_latitude=lat,
        airport_longitude=lon,
        airport_confidence_pct=to_int_pct(payload.get("confidence_pct") or payload.get("airport_confidence_pct")),
        airport_reasoning=reasoning,
        airport_error=None,
    )


def _build_airport_prompt(city: str, country: str, lat: Optional[float], lon: Optional[float]) -> str:
    loc_hint = f" (coordinates: {lat:.5f}, {lon:.5f})" if lat is not None and lon is not None else ""
    return (
        "You are a rigorous web research assistant. Use the web_search tool to search the web, "
        "then answer strictly based on reputable sources (official airport websites, IATA/ICAO directories, "
        "government aviation authorities, or Wikipedia only when it cites official or authoritative sources).\n\n"
        f"Task: Identify the nearest international airport to {city}, {country}{loc_hint}.\n"
        "Definition: International airport = has scheduled international passenger service.\n"
        "Return JSON ONLY with this exact schema and field names:\n"
        "{\n"
        "  \"airport_name\": string,\n"
        "  \"airport_iata\": string | null,\n"
        "  \"airport_icao\": string | null,\n"
        "  \"airport_latitude\": number | null,\n"
        "  \"airport_longitude\": number | null,\n"
        "  \"confidence_pct\": number (0-100),\n"
        "  \"reasoning\": string (1-3 sentences),\n"
        "  \"sources\": [string URL, ...]\n"
        "}"
    )


def _query_openai_for_airport(
    client: OpenAI,
    model: str,
    city: str,
    country: str,
    lat: Optional[float],
    lon: Optional[float],
    request_timeout: Optional[float] = 60.0,
) -> AirportResult:
    try:
        prompt = _build_airport_prompt(city, country, lat, lon)
        response = client.responses.create(
            model=model,
            input=("System: Follow instructions exactly. Do not fabricate sources. Return ONLY JSON.\n\n" + prompt),
            tools=[{"type": "web_search"}],
            timeout=request_timeout,
        )

        # Try structured JSON
        try:
            for item in getattr(response, "output", []) or []:
                for content in getattr(item, "content", []) or []:
                    if getattr(content, "type", None) == "output_json" and getattr(content, "output", None):
                        return _coerce_airport_result(content.output)
        except Exception:
            pass

        # Fallback: parse text
        text: Optional[str] = None
        try:
            text = getattr(response, "output_text", None)
        except Exception:
            text = None
        if not text:
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
            return AirportResult(
                airport_name=None,
                airport_iata=None,
                airport_icao=None,
                airport_latitude=None,
                airport_longitude=None,
                airport_confidence_pct=None,
                airport_reasoning=None,
                airport_error="OpenAI returned no output",
            )

        parsed = _extract_first_json(text)
        if not parsed:
            return AirportResult(
                airport_name=None,
                airport_iata=None,
                airport_icao=None,
                airport_latitude=None,
                airport_longitude=None,
                airport_confidence_pct=None,
                airport_reasoning=text[:5000],
                airport_error="Failed to parse JSON from model output",
            )

        return _coerce_airport_result(parsed)

    except Exception as e:
        return AirportResult(
            airport_name=None,
            airport_iata=None,
            airport_icao=None,
            airport_latitude=None,
            airport_longitude=None,
            airport_confidence_pct=None,
            airport_reasoning=None,
            airport_error=str(e),
        )


def _osrm_route(
    city_lat: float,
    city_lon: float,
    airport_lat: float,
    airport_lon: float,
    base_url: str = "https://router.project-osrm.org",
    request_timeout: float = 30.0,
) -> DriveResult:
    try:
        url = f"{base_url.rstrip('/')}/route/v1/driving/{city_lon:.6f},{city_lat:.6f};{airport_lon:.6f},{airport_lat:.6f}?overview=false&annotations=duration,distance&alternatives=false"
        resp = requests.get(url, timeout=request_timeout)
        if resp.status_code != 200:
            return DriveResult(
                driving_km_to_airport=None,
                driving_time_minutes_to_airport=None,
                driving_confidence_pct=None,
                driving_reasoning=f"OSRM request failed with status {resp.status_code}. Source: {url}",
                driving_error=f"HTTP {resp.status_code} from OSRM",
            )
        data = resp.json()
        routes = (data or {}).get("routes") or []
        if not routes:
            return DriveResult(
                driving_km_to_airport=None,
                driving_time_minutes_to_airport=None,
                driving_confidence_pct=None,
                driving_reasoning=f"No route found by OSRM. Source: {url}",
                driving_error="No route found",
            )
        r0 = routes[0]
        dist_m = float(r0.get("distance", 0.0))
        dur_s = float(r0.get("duration", 0.0))
        km = round(dist_m / 1000.0, 3)
        minutes = round(dur_s / 60.0, 1)
        reasoning = f"Driving route via OSRM. Distance and time derived from OSRM API. Source: {url}"
        # Heuristic confidence: high if both distance and duration present
        conf = 95 if dist_m > 0 and dur_s > 0 else 60
        return DriveResult(
            driving_km_to_airport=km,
            driving_time_minutes_to_airport=minutes,
            driving_confidence_pct=conf,
            driving_reasoning=reasoning,
            driving_error=None,
        )
    except Exception as e:
        return DriveResult(
            driving_km_to_airport=None,
            driving_time_minutes_to_airport=None,
            driving_confidence_pct=None,
            driving_reasoning=None,
            driving_error=str(e),
        )


def enrich_records_with_nearest_airport(
    records: Iterable[Dict],
    model: str = "gpt-5",
    request_timeout: Optional[float] = 60.0,
    osrm_base_url: str = "https://router.project-osrm.org",
    sleep_seconds_between_requests: float = 0.5,
    max_retries: int = 2,
    initial_backoff_seconds: float = 2.0,
    backoff_multiplier: float = 2.0,
    jitter_seconds: float = 0.5,
    limit: Optional[int] = None,
    resume_missing_only: bool = False,
) -> List[Dict]:
    """
    For each record, query OpenAI with web search to determine the nearest international airport, then
    compute driving distance/time via OSRM.

    Adds columns:
      - airport_nearest_name, airport_nearest_iata, airport_nearest_icao
      - airport_nearest_latitude, airport_nearest_longitude
      - airport_confidence_pct, airport_reasoning, airport_error
      - driving_km_to_airport, driving_time_minutes_to_airport
      - driving_confidence_pct, driving_reasoning, driving_error
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    enriched: List[Dict] = []

    processed = 0
    for r in tqdm(list(records), desc="Finding nearest airports", unit="city"):
        if limit is not None and processed >= limit:
            enriched.append(dict(r))
            continue

        # Resume mode: skip rows that already have a non-empty airport name and no error
        if resume_missing_only:
            existing_name = str(r.get("airport_nearest_name") or "").strip()
            existing_err = str(r.get("airport_error") or "").strip()
            if existing_name and not existing_err:
                enriched.append(dict(r))
                continue
        city = str(r.get("name") or r.get("city") or "").strip()
        country = str(r.get("country") or "").strip()
        try:
            lat = float(r.get("latitude")) if r.get("latitude") not in (None, "") else None
            lon = float(r.get("longitude")) if r.get("longitude") not in (None, "") else None
        except Exception:
            lat = None
            lon = None

        # Query with retry/backoff
        attempt = 0
        airport = None
        backoff = max(0.0, float(initial_backoff_seconds))
        while True:
            attempt += 1
            airport = _query_openai_for_airport(
                client=client,
                model=model,
                city=city,
                country=country,
                lat=lat,
                lon=lon,
                request_timeout=request_timeout,
            )
            if airport and not airport.airport_error and (airport.airport_name or airport.airport_iata or airport.airport_icao):
                break
            if attempt > max_retries:
                break
            # backoff with jitter
            sleep_for = backoff + (random.uniform(-jitter_seconds, jitter_seconds) if jitter_seconds > 0 else 0)
            sleep_for = max(0.0, sleep_for)
            time.sleep(sleep_for)
            backoff *= max(1.0, backoff_multiplier)

        new_record = dict(r)

        # Populate airport fields
        if airport.airport_error:
            new_record["airport_nearest_name"] = ""
            new_record["airport_nearest_iata"] = ""
            new_record["airport_nearest_icao"] = ""
            new_record["airport_nearest_latitude"] = ""
            new_record["airport_nearest_longitude"] = ""
            new_record["airport_confidence_pct"] = ""
            new_record["airport_reasoning"] = ""
            new_record["airport_error"] = airport.airport_error
        else:
            new_record["airport_nearest_name"] = airport.airport_name or ""
            new_record["airport_nearest_iata"] = airport.airport_iata or ""
            new_record["airport_nearest_icao"] = airport.airport_icao or ""
            new_record["airport_nearest_latitude"] = airport.airport_latitude if airport.airport_latitude is not None else ""
            new_record["airport_nearest_longitude"] = airport.airport_longitude if airport.airport_longitude is not None else ""
            new_record["airport_confidence_pct"] = (
                airport.airport_confidence_pct if airport.airport_confidence_pct is not None else ""
            )
            new_record["airport_reasoning"] = airport.airport_reasoning or ""
            new_record["airport_error"] = ""

        # Driving distance/time via OSRM if we have coordinates
        if (
            isinstance(new_record.get("airport_nearest_latitude"), (int, float))
            and isinstance(new_record.get("airport_nearest_longitude"), (int, float))
            and isinstance(lat, (int, float))
            and isinstance(lon, (int, float))
        ):
            drive = _osrm_route(
                city_lat=lat,
                city_lon=lon,
                airport_lat=float(new_record["airport_nearest_latitude"]),
                airport_lon=float(new_record["airport_nearest_longitude"]),
                base_url=osrm_base_url,
                request_timeout=30.0,
            )
        else:
            drive = DriveResult(
                driving_km_to_airport=None,
                driving_time_minutes_to_airport=None,
                driving_confidence_pct=None,
                driving_reasoning=None,
                driving_error="Missing coordinates for city or airport",
            )

        if drive.driving_error:
            new_record["driving_km_to_airport"] = ""
            new_record["driving_time_minutes_to_airport"] = ""
            new_record["driving_confidence_pct"] = ""
            new_record["driving_reasoning"] = ""
            new_record["driving_error"] = drive.driving_error
        else:
            new_record["driving_km_to_airport"] = drive.driving_km_to_airport if drive.driving_km_to_airport is not None else ""
            new_record["driving_time_minutes_to_airport"] = (
                drive.driving_time_minutes_to_airport if drive.driving_time_minutes_to_airport is not None else ""
            )
            new_record["driving_confidence_pct"] = (
                drive.driving_confidence_pct if drive.driving_confidence_pct is not None else ""
            )
            new_record["driving_reasoning"] = drive.driving_reasoning or ""
            new_record["driving_error"] = ""

        enriched.append(new_record)

        processed += 1
        if sleep_seconds_between_requests > 0:
            time.sleep(sleep_seconds_between_requests)

    return enriched


