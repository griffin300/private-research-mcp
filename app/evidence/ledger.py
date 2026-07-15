from __future__ import annotations

from app.evidence.citations import make_evidence
from app.evidence.prompt_injection import assess_injection
from app.models import EvidenceRecord, Passage, SourceRecord


def build_evidence(
    ranked: list[tuple[SourceRecord, list[Passage]]], limit: int
) -> list[EvidenceRecord]:
    candidates: list[tuple[SourceRecord, Passage]] = []
    for source, passages in ranked:
        for passage in passages:
            assessment = assess_injection(passage.text)
            passage.injection_risk = assessment.risk  # type: ignore[assignment]
            passage.injection_reasons = assessment.reasons
            if assessment.risk != "high":
                candidates.append((source, passage))
    candidates.sort(key=lambda item: item[1].relevance_score, reverse=True)
    return [
        make_evidence(source, passage, index)
        for index, (source, passage) in enumerate(candidates[:limit], 1)
    ]
