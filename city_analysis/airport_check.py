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
import pandas as pd
import numpy as np
from pathlib import Path


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



def _download_ourairports_csv(cache_path: Path) -> Path:
    url = "https://ourairports.com/data/airports.csv"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "city-analysis/1.0"}
    try:
        # Try with default cert verification (requests+certifi)
        resp = requests.get(url, timeout=60, headers=headers)
        resp.raise_for_status()
        cache_path.write_bytes(resp.content)
        return cache_path
    except Exception:
        # Fallback: attempt with verify=False if local cert store is misconfigured
        try:
            resp = requests.get(url, timeout=60, headers=headers, verify=False)
            resp.raise_for_status()
            cache_path.write_bytes(resp.content)
            return cache_path
        except Exception as e:
            raise e


def _load_airports_dataframe(local_csv: Optional[str]) -> pd.DataFrame:
    """Load and filter the OurAirports dataset to likely international airports.

    Filters:
      - type in {large_airport, medium_airport}
      - scheduled_service == yes
      - iata_code present
      - latitude/longitude present
    """
    if local_csv:
        path = Path(local_csv)
        if not path.exists():
            raise FileNotFoundError(f"Airports dataset not found at {local_csv}")
    else:
        # Cache under ignore/ by default
        path = Path("ignore/airports_ourairports.csv")
        if not path.exists():
            _download_ourairports_csv(path)

    df = pd.read_csv(path)
    # Normalize columns we need
    needed_cols = [
        "name",
        "iata_code",
        "ident",
        "type",
        "latitude_deg",
        "longitude_deg",
        "scheduled_service",
        "iso_country",
    ]
    missing = [c for c in needed_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Airports CSV missing columns: {missing}")

    df = df[
        (df["type"].isin(["large_airport", "medium_airport"]))
        & (df["scheduled_service"].astype(str).str.lower() == "yes")
        & (df["iata_code"].astype(str).str.len() > 0)
        & (df["latitude_deg"].notna())
        & (df["longitude_deg"].notna())
    ][["name", "iata_code", "ident", "latitude_deg", "longitude_deg", "iso_country"]].copy()

    # OurAirports ident is often ICAO for airports. Keep as ICAO when 4 letters.
    df["icao_code"] = df["ident"].where(df["ident"].astype(str).str.len() == 4, None)
    df.rename(columns={"latitude_deg": "lat", "longitude_deg": "lon"}, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _haversine_km_vec(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    # Vectorized Haversine: inputs in degrees
    r = 6371.0
    lat1r = np.radians(lat1)
    lon1r = np.radians(lon1)
    lat2r = np.radians(lat2)
    lon2r = np.radians(lon2)
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(a))
    return r * c


def enrich_records_with_nearest_airport_offline(
    records: Iterable[Dict],
    dataset_csv: Optional[str] = None,
    osrm_base_url: str = "https://router.project-osrm.org",
    topk: int = 3,
    max_radius_km: float = 400.0,
    sleep_seconds_between_requests: float = 0.1,
    limit: Optional[int] = None,
    resume_missing_only: bool = False,
) -> List[Dict]:
    """Offline method using OurAirports dataset + OSRM refinement.

    Strategy:
      1) Load airports once and pre-extract numpy arrays for fast distance calcs.
      2) For each city, select top-K nearest by great-circle distance.
      3) If any within max_radius_km, query OSRM for those and pick min driving time.
         Otherwise, pick nearest by great-circle and skip OSRM.
    """
    airports = _load_airports_dataframe(dataset_csv)
    if airports.empty:
        return [
            {
                **r,
                "airport_nearest_name": "",
                "airport_nearest_iata": "",
                "airport_nearest_icao": "",
                "airport_nearest_latitude": "",
                "airport_nearest_longitude": "",
                "airport_confidence_pct": "",
                "airport_reasoning": "",
                "airport_error": "No airports available after filtering",
                "driving_km_to_airport": "",
                "driving_time_minutes_to_airport": "",
                "driving_confidence_pct": "",
                "driving_reasoning": "",
                "driving_error": "",
            }
            for r in records
        ]

    airport_lats = airports["lat"].to_numpy(dtype=float)
    airport_lons = airports["lon"].to_numpy(dtype=float)

    enriched: List[Dict] = []
    processed = 0
    for r in tqdm(list(records), desc="Nearest airports (offline)", unit="city"):
        if limit is not None and processed >= limit:
            enriched.append(dict(r))
            continue

        if resume_missing_only:
            existing_name = str(r.get("airport_nearest_name") or "").strip()
            existing_err = str(r.get("airport_error") or "").strip()
            if existing_name and not existing_err:
                enriched.append(dict(r))
                continue

        # Parse inputs
        try:
            city = str(r.get("name") or r.get("city") or "").strip()
            country = str(r.get("country") or "").strip()
            lat = float(r.get("latitude")) if r.get("latitude") not in (None, "") else None
            lon = float(r.get("longitude")) if r.get("longitude") not in (None, "") else None
        except Exception:
            lat = None
            lon = None

        new_record = dict(r)

        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            # Missing city coordinates
            new_record["airport_nearest_name"] = ""
            new_record["airport_nearest_iata"] = ""
            new_record["airport_nearest_icao"] = ""
            new_record["airport_nearest_latitude"] = ""
            new_record["airport_nearest_longitude"] = ""
            new_record["airport_confidence_pct"] = ""
            new_record["airport_reasoning"] = ""
            new_record["airport_error"] = "Missing city coordinates"
            new_record["driving_km_to_airport"] = ""
            new_record["driving_time_minutes_to_airport"] = ""
            new_record["driving_confidence_pct"] = ""
            new_record["driving_reasoning"] = ""
            new_record["driving_error"] = ""
            enriched.append(new_record)
            processed += 1
            continue

        # Top-K by crow-flies
        dists = _haversine_km_vec(lat, lon, airport_lats, airport_lons)
        k = max(1, min(topk, dists.shape[0]))
        idxs = np.argpartition(dists, k - 1)[:k]
        # Sort those K by distance
        idxs = idxs[np.argsort(dists[idxs])]

        # Filter by radius for OSRM
        within = [i for i in idxs.tolist() if float(dists[i]) <= float(max_radius_km)]

        chosen_idx = None
        drive: Optional[DriveResult] = None
        driving_attempted = False
        if within:
            best = None
            for i in within:
                a_lat = float(airport_lats[i])
                a_lon = float(airport_lons[i])
                dr = _osrm_route(
                    city_lat=lat,
                    city_lon=lon,
                    airport_lat=a_lat,
                    airport_lon=a_lon,
                    base_url=osrm_base_url,
                    request_timeout=30.0,
                )
                driving_attempted = True
                if dr.driving_error:
                    continue
                if best is None or (dr.driving_time_minutes_to_airport or 0) < (best[1].driving_time_minutes_to_airport or 0):
                    best = (i, dr)
                if sleep_seconds_between_requests > 0:
                    time.sleep(sleep_seconds_between_requests)
            if best is not None:
                chosen_idx, drive = best
        # Fallback to nearest by crow-flies if no OSRM success
        if chosen_idx is None:
            chosen_idx = int(idxs[0])

        a = airports.iloc[chosen_idx]
        new_record["airport_nearest_name"] = str(a["name"]) if pd.notna(a["name"]) else ""
        new_record["airport_nearest_iata"] = str(a["iata_code"]) if pd.notna(a["iata_code"]) else ""
        new_record["airport_nearest_icao"] = str(a["icao_code"]) if pd.notna(a["icao_code"]) else ""
        new_record["airport_nearest_latitude"] = float(a["lat"]) if pd.notna(a["lat"]) else ""
        new_record["airport_nearest_longitude"] = float(a["lon"]) if pd.notna(a["lon"]) else ""
        new_record["airport_confidence_pct"] = 90 if within else 75
        method = "OSRM driving among top-K" if drive and not drive.driving_error else "crow-flies nearest"
        new_record["airport_reasoning"] = (
            f"Selected by {method} from OurAirports dataset (scheduled service)."
        )
        new_record["airport_error"] = "" if (within or not driving_attempted) else "OSRM failed for all candidates"

        # Driving fields
        if drive and not drive.driving_error:
            new_record["driving_km_to_airport"] = drive.driving_km_to_airport if drive.driving_km_to_airport is not None else ""
            new_record["driving_time_minutes_to_airport"] = (
                drive.driving_time_minutes_to_airport if drive.driving_time_minutes_to_airport is not None else ""
            )
            new_record["driving_confidence_pct"] = (
                drive.driving_confidence_pct if drive.driving_confidence_pct is not None else ""
            )
            new_record["driving_reasoning"] = drive.driving_reasoning or ""
            new_record["driving_error"] = ""
        else:
            # No OSRM driving if beyond radius or OSRM failed
            new_record["driving_km_to_airport"] = ""
            new_record["driving_time_minutes_to_airport"] = ""
            new_record["driving_confidence_pct"] = ""
            new_record["driving_reasoning"] = ""
            if not within:
                new_record["driving_error"] = "No airport within max_radius_km; driving not computed"
            else:
                new_record["driving_error"] = "OSRM failed for all candidates"

        enriched.append(new_record)
        processed += 1

    return enriched

