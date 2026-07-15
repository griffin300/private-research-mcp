from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.models import SearchMode


@dataclass(frozen=True, slots=True)
class SearchBudget:
    queries: int
    raw_results: int
    pages: int
    passages: int
    rounds: int
    browser_pages: int


DEFAULT_BUDGETS: dict[SearchMode, SearchBudget] = {
    SearchMode.QUICK: SearchBudget(3, 15, 5, 10, 1, 0),
    SearchMode.STANDARD: SearchBudget(6, 40, 10, 20, 2, 1),
    SearchMode.DEEP: SearchBudget(15, 100, 25, 40, 4, 3),
}


def budget_for(mode: SearchMode, settings: Settings | None = None) -> SearchBudget:
    if settings is None:
        return DEFAULT_BUDGETS[mode]
    prefix = mode.value
    return SearchBudget(
        queries=getattr(settings, f"{prefix}_queries"),
        raw_results=getattr(settings, f"{prefix}_raw_results"),
        pages=getattr(settings, f"{prefix}_pages"),
        passages=getattr(settings, f"{prefix}_passages"),
        rounds=getattr(settings, f"{prefix}_rounds"),
        browser_pages=getattr(settings, f"{prefix}_browser_pages"),
    )
