from __future__ import annotations

import re

from app.models import SearchMode


def select_search_mode(query: str) -> SearchMode:
    """Choose a quality-first research depth; Quick remains an explicit latency option."""
    normalized = " ".join(query.casefold().split())
    deep_signals = (
        r"\b(?:deep|comprehensive|exhaustive|investigate|systematic)\b",
        r"\b(?:conflict|contradiction|disagree|multiple independent sources)\b",
        r"\b(?:design|architecture|threat model|trade-?offs?)\b",
        r"\b(?:analy[sz]e|evaluate|assess|synthesi[sz]e|optimi[sz]e|improve)\b",
        r"\b(?:latest|current|today|recent|as of|right now)\b",
        r"\b(?:evidence|sources|research|citations?)\b",
    )
    if any(re.search(pattern, normalized) for pattern in deep_signals):
        return SearchMode.DEEP
    return SearchMode.STANDARD


__all__ = ["select_search_mode"]
