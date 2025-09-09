from __future__ import annotations

from typing import Dict, Iterable, List


def top_n_by_population(places: Iterable[Dict], n: int = 20) -> List[Dict]:
    return sorted(places, key=lambda r: int(r.get("population") or 0), reverse=True)[:n]


def summarize(places: Iterable[Dict]) -> Dict:
    items = list(places)
    total = len(items)
    with_population = sum(1 for r in items if int(r.get("population") or 0) > 0)
    return {
        "total_places": total,
        "with_population": with_population,
        "missing_population": total - with_population,
    }
