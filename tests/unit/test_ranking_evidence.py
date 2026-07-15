from datetime import UTC, datetime

from app.evidence.citations import make_evidence
from app.evidence.contradictions import detect_contradictions
from app.evidence.coverage import analyze_coverage
from app.evidence.ledger import build_evidence
from app.models import EvidenceRecord, Passage, SourceRecord
from app.ranking.lexical import rank_passages


def source(identifier: str, domain: str = "example.com") -> SourceRecord:
    return SourceRecord(
        source_id=identifier,
        url=f"https://{domain}/x",
        title="Source",
        domain=domain,
        retrieved_at=datetime.now(UTC),
        source_type="official_documentation",
        quality_score=0.9,
        relevance_score=0.8,
        fetch_method="http",
        content_hash=identifier,
    )


def test_passage_ranking_and_citation() -> None:
    passages = [
        Passage(text="unrelated weather report", start_offset=0, end_offset=24),
        Passage(
            text="MCP streamable HTTP is the recommended transport", start_offset=25, end_offset=74
        ),
    ]
    ranked = rank_passages("MCP recommended transport", passages)
    record = make_evidence(source("src_001"), ranked[0], 1)
    assert "streamable" in ranked[0].text
    assert record.citation == "[src_001, ev_001]"


def test_coverage_reports_missing_topics() -> None:
    evidence = [
        make_evidence(
            source("src_001"),
            Passage(text="MCP uses HTTP transport", start_offset=0, end_offset=23),
            1,
        )
    ]
    report = analyze_coverage(
        ["MCP transport", "Docker DNS isolation"], evidence, [source("src_001")]
    )
    assert "MCP transport" in report.covered_topics
    assert "Docker DNS isolation" in report.missing_topics


def test_numeric_contradiction_detection() -> None:
    records = [
        EvidenceRecord(
            evidence_id="ev_001",
            source_id="src_001",
            text="Product speed result is 10 ms.",
            start_offset=0,
            end_offset=30,
            relevance_score=1,
            citation="[src_001, ev_001]",
        ),
        EvidenceRecord(
            evidence_id="ev_002",
            source_id="src_002",
            text="Product speed result is 20 ms.",
            start_offset=0,
            end_offset=30,
            relevance_score=1,
            citation="[src_002, ev_002]",
        ),
    ]
    assert detect_contradictions(records)


def test_global_evidence_ranking_keeps_distinct_supporting_sources() -> None:
    duplicate = "MCP transport production recommendation Streamable HTTP exact support"
    ranked = [
        (
            source("src_001", "docs.example.com"),
            [
                Passage(text=duplicate, start_offset=0, end_offset=len(duplicate)),
                Passage(text=duplicate + " repeated", start_offset=70, end_offset=150),
            ],
        ),
        (
            source("src_002", "spec.example.org"),
            [
                Passage(
                    text="Independent specification confirms the production transport.",
                    start_offset=0,
                    end_offset=59,
                )
            ],
        ),
    ]
    evidence = build_evidence(ranked, 2, query="production transport recommendation")
    assert {item.source_id for item in evidence} == {"src_001", "src_002"}
