from datetime import UTC, datetime

from app.evidence.citations import make_evidence
from app.evidence.contradictions import detect_contradictions
from app.evidence.coverage import analyze_coverage
from app.evidence.ledger import build_evidence
from app.models import EvidenceRecord, Passage, SearchResult, SourceRecord
from app.orchestration.pipeline import _select_fetch_candidates
from app.ranking.lexical import meaningful_tokens, rank_passages


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


def test_coverage_requires_both_terms_for_a_short_topic() -> None:
    evidence = [
        make_evidence(
            source("src_001"),
            Passage(text="MCP is mentioned alone.", start_offset=0, end_offset=23),
            1,
        )
    ]
    report = analyze_coverage(["MCP transport"], evidence, [source("src_001")])
    assert report.missing_topics == ["MCP transport"]


def test_generic_proximity_ranking_prefers_related_query_terms() -> None:
    passages = [
        Passage(
            text="Production guidance appears here. " + "filler " * 80 + "Transport is elsewhere.",
            start_offset=0,
            end_offset=600,
        ),
        Passage(
            text="The production transport recommendation is Streamable HTTP.",
            start_offset=601,
            end_offset=660,
        ),
    ]
    ranked = rank_passages("production transport recommendation", passages)
    assert ranked[0].text.startswith("The production transport")


def test_lexical_normalization_matches_common_inflections() -> None:
    assert meaningful_tokens("recommended transports policies") == [
        "recommend",
        "transport",
        "policy",
    ]


def test_fetch_selection_keeps_top_result_and_rejects_irrelevant_primary() -> None:
    candidates = [
        SearchResult(
            url="https://relevant.example/result",
            canonical_url="https://relevant.example/result",
            title="Top result",
            domain="relevant.example",
            preliminary_score=1.0,
        ),
        SearchResult(
            url="https://weak.example/docs/page",
            canonical_url="https://weak.example/docs/page",
            title="Irrelevant docs",
            domain="weak.example",
            preliminary_score=0.01,
        ),
        SearchResult(
            url="https://second.example/result",
            canonical_url="https://second.example/result",
            title="Relevant second result",
            domain="second.example",
            preliminary_score=0.8,
        ),
    ]
    assert _select_fetch_candidates(candidates, 1) == [candidates[0]]
    assert _select_fetch_candidates(candidates, 2) == [candidates[0], candidates[2]]
