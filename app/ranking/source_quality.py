from __future__ import annotations

from urllib.parse import urlsplit

from app.models import SearchResult
from app.ranking.lexical import meaningful_tokens


def source_type(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    path = urlsplit(url).path.lower()
    if host.endswith(".gov") or host.endswith(".edu"):
        return "primary_institution"
    if "docs." in host or "/docs/" in path or "/documentation/" in path:
        return "official_documentation"
    if "github.com" in host and "/issues/" in path:
        return "issue_tracker"
    if "github.com" in host:
        return "source_repository"
    if any(value in path for value in ("paper", "article", "research")):
        return "publication"
    return "web_page"


def score_search_result(query: str, result: SearchResult) -> float:
    query_terms = set(meaningful_tokens(query))
    haystack = set(meaningful_tokens(f"{result.title} {result.snippet}"))
    overlap = len(query_terms & haystack) / max(1, len(query_terms))
    engine_agreement = min(0.15, 0.04 * max(0, len(result.engines) - 1))
    type_bonus = (
        0.12
        if source_type(result.url) in {"official_documentation", "primary_institution"}
        else 0.0
    )
    spam_penalty = (
        0.18
        if sum(word in result.title.casefold() for word in ("best", "top 10", "ultimate guide"))
        >= 2
        else 0.0
    )
    return round(
        max(
            0.0,
            min(
                1.0,
                0.55 * overlap
                + 0.25 * result.search_score
                + engine_agreement
                + type_bonus
                - spam_penalty,
            ),
        ),
        4,
    )


def explain_source_quality(result: SearchResult, *, dated: bool) -> list[str]:
    kind = source_type(result.url)
    explanations = [
        f"URL/content classification: {kind}",
        f"Pre-fetch query/source score: {result.preliminary_score:.4f}",
        f"Search-engine agreement: {max(1, len(result.engines))} engine(s)",
    ]
    explanations.append(
        "Publication or update date available for freshness scoring"
        if dated
        else "No reliable publication/update date; conservative freshness score applied"
    )
    return explanations
