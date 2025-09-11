from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from openai import OpenAI
from tqdm import tqdm


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


