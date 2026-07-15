from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx
from dateutil import parser as date_parser

from app.models import SearchResult


class SearxngError(RuntimeError):
    pass


class SearxngBackend:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        params: dict[str, str | int] = {
            "q": query,
            "format": "json",
            "language": language,
            "safesearch": 1,
            "categories": _categories_for_query(query),
        }
        if recency_days is not None:
            params["time_range"] = (
                "day" if recency_days <= 1 else "month" if recency_days <= 31 else "year"
            )
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.get(f"{self.base_url}/search", params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearxngError(f"search backend unavailable: {type(exc).__name__}") from exc
        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list):
            raise SearxngError("search backend returned an invalid response")
        return [self._parse(item, index) for index, item in enumerate(raw_results[:limit])]

    @staticmethod
    def _parse(item: dict[str, Any], index: int) -> SearchResult:
        raw_date = item.get("publishedDate") or item.get("published_date")
        parsed_date: datetime | None = None
        if isinstance(raw_date, str):
            try:
                parsed_date = date_parser.parse(raw_date)
            except (ValueError, OverflowError):
                parsed_date = None
        raw_engines = item.get("engines")
        engines: list[Any] = raw_engines if isinstance(raw_engines, list) else []
        engine = str(item.get("engine") or (engines[0] if engines else "unknown"))
        return SearchResult(
            url=str(item.get("url", "")),
            title=str(item.get("title", "Untitled")),
            snippet=str(item.get("content", "")),
            rank=index + 1,
            engine=engine,
            engines=[str(value) for value in engines] or [engine],
            published_at=parsed_date,
            search_score=max(0.0, 1.0 - index / 20),
        )

    async def health(self) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 5), trust_env=False) as client:
                response = await client.get(f"{self.base_url}/healthz")
                if response.status_code == 404:
                    response = await client.get(self.base_url)
            return {
                "status": "healthy" if response.is_success else "unhealthy",
                "code": response.status_code,
            }
        except httpx.HTTPError as exc:
            return {"status": "unhealthy", "error": type(exc).__name__}


def _categories_for_query(query: str) -> str:
    categories = ["general"]
    if re.search(
        r"\b(?:api|code|curl|database|docker|git|http|https|java|javascript|linux|mcp|"
        r"package|protocol|python|release|rfc|sdk|software|sql|typescript|version|windows)\b",
        query,
        re.IGNORECASE,
    ):
        categories.append("it")
    if re.search(
        r"\b(?:arxiv|clinical|doi|experiment|journal|paper|peer-reviewed|research|science|study)\b",
        query,
        re.IGNORECASE,
    ):
        categories.append("science")
    if re.search(
        r"\b(?:breaking|election|headline|news|today|this week)\b",
        query,
        re.IGNORECASE,
    ):
        categories.append("news")
    return ",".join(categories)
