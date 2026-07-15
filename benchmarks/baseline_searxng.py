from __future__ import annotations

import time

from app.search.searxng import SearxngBackend


async def run_baseline(
    backend: SearxngBackend, question: str, limit: int = 10
) -> dict[str, object]:
    started = time.monotonic()
    results = await backend.search(question, language="en", recency_days=None, limit=limit)
    return {
        "mode": "raw_searxng",
        "latency_seconds": round(time.monotonic() - started, 3),
        "sources": [result.model_dump(mode="json") for result in results],
        "evidence": [],
        "coverage": None,
    }
