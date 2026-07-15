from __future__ import annotations

import time

from app.models import SearchResult
from app.orchestration.pipeline import ResearchPipeline


async def run_baseline(
    pipeline: ResearchPipeline,
    question: str,
    limit: int = 10,
    exact_results: list[SearchResult] | None = None,
) -> dict[str, object]:
    started = time.monotonic()
    results = (
        exact_results[:limit]
        if exact_results is not None
        else await pipeline.search_exact(question, language="en", recency_days=None, limit=limit)
    )
    return {
        "mode": "raw_searxng",
        "latency_seconds": round(time.monotonic() - started, 3),
        "sources": [result.model_dump(mode="json") for result in results],
        "evidence": [],
        "coverage": None,
    }
