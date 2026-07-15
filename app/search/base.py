from __future__ import annotations

from typing import Protocol

from app.models import SearchResult


class SearchBackend(Protocol):
    async def search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]: ...

    async def health(self) -> dict[str, object]: ...
