from __future__ import annotations

from app.evidence.citations import make_evidence
from app.evidence.prompt_injection import assess_injection
from app.models import EvidenceRecord, Passage, SourceRecord
from app.ranking.lexical import (
    meaningful_tokens,
    rank_passages,
    rank_passages_for_queries,
    tokenize,
)


def build_evidence(
    ranked: list[tuple[SourceRecord, list[Passage]]],
    limit: int,
    *,
    query: str | None = None,
    queries: list[str] | None = None,
) -> list[EvidenceRecord]:
    candidates: list[tuple[SourceRecord, Passage]] = []
    for source, passages in ranked:
        for passage in passages:
            assessment = assess_injection(passage.text)
            passage.injection_risk = assessment.risk  # type: ignore[assignment]
            passage.injection_reasons = assessment.reasons
            if assessment.risk != "high":
                candidates.append((source, passage))
    if candidates and queries:
        rank_passages_for_queries(queries, [passage for _, passage in candidates])
    elif query and candidates:
        rank_passages(query, [passage for _, passage in candidates])
    candidates = _select_diverse(candidates, limit, queries=queries)
    return [
        make_evidence(source, passage, index)
        for index, (source, passage) in enumerate(candidates, 1)
    ]


def _select_diverse(
    candidates: list[tuple[SourceRecord, Passage]],
    limit: int,
    *,
    queries: list[str] | None = None,
) -> list[tuple[SourceRecord, Passage]]:
    if not candidates:
        return []

    def base_score(item: tuple[SourceRecord, Passage]) -> float:
        source, passage = item
        return (
            0.65 * passage.relevance_score
            + 0.25 * source.quality_score
            + 0.10 * source.relevance_score
        )

    maximum = max(base_score(item) for item in candidates)
    remaining = list(candidates)
    selected: list[tuple[SourceRecord, Passage]] = []
    selected_tokens: list[set[str]] = []
    source_counts: dict[str, int] = {}

    def select(index: int) -> None:
        source, passage = remaining.pop(index)
        selected.append((source, passage))
        selected_tokens.append(set(tokenize(passage.text)))
        source_counts[source.source_id] = source_counts.get(source.source_id, 0) + 1

    for query in queries or []:
        if len(selected) >= limit:
            break
        terms = set(meaningful_tokens(query))
        required = 1.0 if len(terms) <= 2 else 0.60
        facet_matches = [
            (index, len(terms & set(meaningful_tokens(passage.text))) / max(1, len(terms)))
            for index, (_, passage) in enumerate(remaining)
        ]
        facet_matches = [
            (index, coverage) for index, coverage in facet_matches if coverage >= required
        ]
        if facet_matches:
            best_index, _ = max(
                facet_matches,
                key=lambda item: (item[1], base_score(remaining[item[0]])),
            )
            select(best_index)

    remaining = [item for item in remaining if base_score(item) >= maximum * 0.30]

    while remaining and len(selected) < limit:
        unseen_sources = {
            source.source_id for source, _ in remaining if source.source_id not in source_counts
        }
        require_new_source = bool(unseen_sources)
        eligible_indexes = [
            index
            for index, (source, _) in enumerate(remaining)
            if not require_new_source or source.source_id not in source_counts
        ]
        best_index = 0
        best_score = -1.0
        for index in eligible_indexes:
            source, passage = remaining[index]
            terms = set(tokenize(passage.text))
            similarity = max(
                (_jaccard(terms, existing) for existing in selected_tokens), default=0.0
            )
            base = base_score((source, passage))
            score = base - 0.25 * similarity - 0.05 * source_counts.get(source.source_id, 0)
            if score > best_score:
                best_index = index
                best_score = score
        select(best_index)
    return selected


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))
