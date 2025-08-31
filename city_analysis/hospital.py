from __future__ import annotations

import json
import os
from typing import Dict, Iterable, List

from openai import OpenAI


def _query_hospital(client: OpenAI, city: str, country: str) -> Dict[str, str | float]:
    prompt = (
        "You are checking if a city has at least one hospital. "
        "Search the web and respond in JSON with keys: has_hospital ('yes' or 'no'), "
        "confidence (0-100 integer representing percentage), and reasoning "
        "(concise justification including at least one reputable link). "
        f"City: {city}, Country: {country}."
    )
    try:
        response = client.responses.create(
            model="gpt-5",
            input=prompt,
            web_search=True,
        )
        text = response.output_text
        data = json.loads(text)
        has_hospital = str(data.get("has_hospital", "")).lower()
        confidence = data.get("confidence", "")
        reasoning = data.get("reasoning", "")
        return {
            "has_hospital": has_hospital,
            "hospital_confidence": confidence,
            "hospital_reasoning": reasoning,
        }
    except Exception as e:  # capture API errors
        return {
            "has_hospital": "error",
            "hospital_confidence": "",
            "hospital_reasoning": str(e),
        }


def add_hospital_info(records: Iterable[Dict]) -> List[Dict]:
    api_key = os.getenv("OPENAI_API_KEY")
    try:
        client = OpenAI(api_key=api_key)
    except Exception as e:
        enriched_error: List[Dict] = []
        for record in records:
            record.update({
                "has_hospital": "error",
                "hospital_confidence": "",
                "hospital_reasoning": str(e),
            })
            enriched_error.append(record)
        return enriched_error

    enriched: List[Dict] = []
    for record in records:
        info = _query_hospital(client, record.get("name", ""), record.get("country", ""))
        record.update(info)
        enriched.append(record)
    return enriched
