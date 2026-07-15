from __future__ import annotations

from app.evidence.citations import make_evidence
from app.evidence.prompt_injection import assess_injection
from app.models import EvidenceRecord, Passage, SourceRecord
from app.ranking.lexical import rank_passages, tokenize


def build_evidence(
    ranked: list[tuple[SourceRecord, list[Passage]]], limit: int, *, query: str | None = None
) -> list[EvidenceRecord]:
    candidates: list[tuple[SourceRecord, Passage]] = []
    for source, passages in ranked:
        for passage in passages:
            assessment = assess_injection(passage.text)
            passage.injection_risk = assessment.risk  # type: ignore[assignment]
            passage.injection_reasons = assessment.reasons
            if assessment.risk != "high":
                candidates.append((source, passage))
    if query and candidates:
        rank_passages(query, [passage for _, passage in candidates])
    candidates = _select_diverse(candidates, limit)
    return [
        make_evidence(source, passage, index)
        for index, (source, passage) in enumerate(candidates, 1)
    ]


def _select_diverse(
    candidates: list[tuple[SourceRecord, Passage]], limit: int
) -> list[tuple[SourceRecord, Passage]]:
    remaining = list(candidates)
    selected: list[tuple[SourceRecord, Passage]] = []
    selected_tokens: list[set[str]] = []
    source_counts: dict[str, int] = {}
    unique_source_count = len({source.source_id for source, _ in remaining})
    while remaining and len(selected) < limit:
        require_new_source = len(source_counts) < min(limit, unique_source_count)
        eligible = [
            index
            for index, (source, _) in enumerate(remaining)
            if not require_new_source or source.source_id not in source_counts
        ]
        best_index = 0
        best_score = -1.0
        for index in eligible:
            source, passage = remaining[index]
            terms = set(tokenize(passage.text))
            similarity = max(
                (_jaccard(terms, existing) for existing in selected_tokens), default=0.0
            )
            base = (
                0.65 * passage.relevance_score
                + 0.25 * source.quality_score
                + 0.10 * source.relevance_score
            )
            score = base - 0.25 * similarity - 0.05 * source_counts.get(source.source_id, 0)
            if score > best_score:
                best_index = index
                best_score = score
        source, passage = remaining.pop(best_index)
        selected.append((source, passage))
        selected_tokens.append(set(tokenize(passage.text)))
        source_counts[source.source_id] = source_counts.get(source.source_id, 0) + 1
    return selected


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))
