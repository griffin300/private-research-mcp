from __future__ import annotations

from urllib.parse import urlsplit

from app.models import SearchResult
from app.ranking.lexical import meaningful_tokens
from app.search.official_sources import (
    distinctive_anchor_coverage,
    distinctive_query_tokens,
    domain_matches_authority,
)

_OFFICIAL_DOCUMENTATION_DOMAINS = {
    "curl.se",
    "docs.python.org",
    "everything.curl.dev",
    "ietf.org",
    "iana.org",
    "modelcontextprotocol.io",
    "peps.python.org",
    "py.sdk.modelcontextprotocol.io",
    "python.org",
    "rfc-editor.org",
    "sqlite.org",
}
_QUERY_ALIASES = {
    "mcp": {"model", "context", "protocol"},
    "sdk": {"software", "development", "kit"},
    "wal": {"write", "ahead", "log"},
}


def source_type(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    path = urlsplit(url).path.lower()
    if host.endswith(".gov") or host.endswith(".edu"):
        return "primary_institution"
    if any(host == domain or host.endswith(f".{domain}") for domain in _OFFICIAL_DOCUMENTATION_DOMAINS):
        return "official_documentation"
    if "docs." in host or "/docs/" in path or "/documentation/" in path:
        return "official_documentation"
    is_github = (
        host == "github.com"
        or host.endswith(".github.com")
        or host == "raw.githubusercontent.com"
    )
    if is_github and "/issues/" in path:
        return "issue_tracker"
    if is_github:
        return "source_repository"
    if any(value in path for value in ("paper", "article", "research")):
        return "publication"
    return "web_page"


def score_search_result(query: str, result: SearchResult) -> float:
    query_terms = set(meaningful_tokens(query))
    expanded_query_terms = set(query_terms)
    for term in query_terms:
        expanded_query_terms.update(_QUERY_ALIASES.get(term, set()))
    parsed = urlsplit(result.url)
    url_text = f"{parsed.hostname or ''} {parsed.path.replace('/', ' ')}"
    haystack = set(meaningful_tokens(f"{result.title} {result.snippet} {url_text}"))
    overlap = len(query_terms & haystack) / max(1, len(query_terms))
    expanded_overlap = len(expanded_query_terms & haystack) / max(1, len(expanded_query_terms))
    overlap = max(overlap, expanded_overlap)
    anchors = distinctive_query_tokens(query)
    anchor_coverage = distinctive_anchor_coverage(
        query, f"{result.title} {result.snippet} {result.url}"
    )
    anchor_bonus = 0.20 * anchor_coverage if anchors else 0.0
    engine_agreement = min(0.15, 0.04 * max(0, len(result.engines) - 1))
    kind = source_type(result.url)
    authority_match = domain_matches_authority(query, result.url)
    type_bonus = 0.0
    if authority_match:
        type_bonus = 0.22
    elif kind in {"official_documentation", "primary_institution", "source_repository"}:
        type_bonus = 0.06 if overlap >= 0.25 else 0.0
    missing_anchor_penalty = 0.18 * (1.0 - anchor_coverage) if anchors else 0.0
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
                0.42 * overlap
                + 0.20 * result.search_score
                + anchor_bonus
                + engine_agreement
                + type_bonus
                - missing_anchor_penalty
                - spam_penalty,
            ),
        ),
        4,
    )


def explain_source_quality(result: SearchResult, *, query: str, dated: bool) -> list[str]:
    kind = source_type(result.url)
    explanations = [
        f"URL/content classification: {kind}",
        f"Pre-fetch query/source score: {result.preliminary_score:.4f}",
        "Query-aligned authority: "
        + ("yes" if domain_matches_authority(query, result.url) else "no"),
        f"Search-engine agreement: {max(1, len(result.engines))} engine(s)",
    ]
    explanations.append(
        "Publication or update date available for freshness scoring"
        if dated
        else "No reliable publication/update date; conservative freshness score applied"
    )
    return explanations
