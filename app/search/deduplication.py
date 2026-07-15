from __future__ import annotations

from difflib import SequenceMatcher

from app.models import SearchResult


def deduplicate_results(results: list[SearchResult]) -> list[SearchResult]:
    kept: list[SearchResult] = []
    for candidate in results:
        duplicate: SearchResult | None = None
        for existing in kept:
            same_url = candidate.canonical_url == existing.canonical_url
            title_match = (
                SequenceMatcher(None, candidate.title.casefold(), existing.title.casefold()).ratio()
                >= 0.93
            )
            snippet_match = (
                bool(candidate.snippet and existing.snippet)
                and SequenceMatcher(
                    None, candidate.snippet.casefold(), existing.snippet.casefold()
                ).ratio()
                >= 0.94
            )
            if same_url or (candidate.domain == existing.domain and title_match) or snippet_match:
                duplicate = existing
                break
        if duplicate:
            duplicate.engines = sorted(set(duplicate.engines + candidate.engines))
            duplicate.search_score = max(duplicate.search_score, candidate.search_score)
            if len(candidate.snippet) > len(duplicate.snippet):
                duplicate.snippet = candidate.snippet
        else:
            kept.append(candidate)
    return kept
