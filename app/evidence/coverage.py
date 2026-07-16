from __future__ import annotations

from typing import Literal

from app.models import CoverageReport, EvidenceRecord, SourceRecord
from app.ranking.lexical import meaningful_tokens


def analyze_coverage(
    topics: list[str], evidence: list[EvidenceRecord], sources: list[SourceRecord]
) -> CoverageReport:
    covered: list[str] = []
    missing: list[str] = []
    evidence_tokens = [
        set(meaningful_tokens(item.text)) for item in evidence if item.injection_risk != "high"
    ]
    for topic in topics:
        terms = set(meaningful_tokens(topic))
        best = max(
            (len(terms & tokens) / max(1, len(terms)) for tokens in evidence_tokens), default=0.0
        )
        required = 1.0 if len(terms) <= 2 else 0.60
        (covered if best >= required else missing).append(topic)
    topic_score = len(covered) / max(1, len(topics))
    evidence_sources = {
        item.source_id for item in evidence if item.injection_risk != "high"
    }
    supported_sources = [
        source
        for source in sources
        if source.source_id in evidence_sources and source.relevance_score >= 0.18
    ]
    supported_domains = {source.domain for source in supported_sources}
    diversity = min(1.0, len(supported_domains) / 3)
    evidence_strength = min(1.0, len(evidence) / 8)
    score = round(0.55 * topic_score + 0.25 * diversity + 0.20 * evidence_strength, 3)
    status: Literal["insufficient", "weak", "moderate", "strong"]
    if score >= 0.8:
        status = "strong"
    elif score >= 0.6:
        status = "moderate"
    elif score >= 0.3:
        status = "weak"
    else:
        status = "insufficient"
    primary = any(
        source.relevance_score >= 0.25
        and source.source_type
        in {"official_documentation", "primary_institution", "source_repository"}
        for source in supported_sources
    )
    return CoverageReport(
        score=score,
        status=status,
        covered_topics=covered,
        missing_topics=missing,
        primary_source_present=primary,
        independent_source_count=len(supported_domains),
    )
