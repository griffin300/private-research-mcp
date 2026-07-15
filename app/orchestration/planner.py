from __future__ import annotations

import json
from typing import Any

import httpx

from app.search.query_expansion import HeuristicQueryPlanner, QueryPlan


class EnhancedPlannerError(RuntimeError):
    pass


class EnhancedQueryPlanner:
    """Optional OpenAI-compatible planner restricted to a configured local endpoint."""

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self.model = model
        self.timeout = timeout

    async def plan(self, question: str, fallback: QueryPlan, limit: int) -> QueryPlan:
        request = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 600,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only JSON with queries (array of search strings), topics "
                        "(array), and time_sensitive (boolean). Do not answer the question."
                    ),
                },
                {"role": "user", "content": question[:4000]},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(self.url, json=request)
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
            content = str(payload["choices"][0]["message"]["content"])
            parsed = json.loads(_strip_fence(content))
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise EnhancedPlannerError(type(exc).__name__) from exc
        queries = _clean_strings(parsed.get("queries"), 500)
        topics = _clean_strings(parsed.get("topics"), 200)
        if not queries:
            raise EnhancedPlannerError("planner returned no queries")
        combined = list(dict.fromkeys([*queries, *fallback.queries]))[:limit]
        return QueryPlan(
            original=fallback.original,
            queries=combined,
            topics=topics[:8] or fallback.topics,
            time_sensitive=bool(parsed.get("time_sensitive", fallback.time_sensitive)),
        )


def _clean_strings(value: object, maximum_length: int) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [" ".join(str(item).split())[:maximum_length] for item in value]
    return [item for item in cleaned if item]


def _strip_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        stripped = stripped.rsplit("```", 1)[0]
    return stripped.strip()


__all__ = [
    "EnhancedPlannerError",
    "EnhancedQueryPlanner",
    "HeuristicQueryPlanner",
    "QueryPlan",
]
