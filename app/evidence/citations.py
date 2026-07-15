from __future__ import annotations

from app.models import EvidenceRecord, Passage, SourceRecord


def make_evidence(source: SourceRecord, passage: Passage, index: int) -> EvidenceRecord:
    evidence_id = f"ev_{index:03d}"
    return EvidenceRecord(
        evidence_id=evidence_id,
        source_id=source.source_id,
        heading=passage.heading,
        text=passage.text,
        start_offset=passage.start_offset,
        end_offset=passage.end_offset,
        relevance_score=passage.relevance_score,
        injection_risk=passage.injection_risk,
        citation=f"[{source.source_id}, {evidence_id}]",
    )
