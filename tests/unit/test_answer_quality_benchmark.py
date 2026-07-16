import json
from pathlib import Path

from benchmarks.answer_quality import score_result


def test_gold_fact_scoring_rewards_supported_cited_primary_evidence() -> None:
    item = {
        "assertions": [
            {"label": "transport", "patterns": [r"streamable\s+http"]},
            {"label": "production", "patterns": [r"production"]},
        ],
        "preferred_domains": ["example.org"],
    }
    result = {
        "sources": [
            {
                "source_id": "src_001",
                "url": "https://docs.example.org/mcp",
                "domain": "docs.example.org",
            }
        ],
        "evidence": [
            {
                "evidence_id": "ev_001",
                "source_id": "src_001",
                "text": "Streamable HTTP is recommended for production deployments.",
                "start_offset": 10,
                "end_offset": 70,
                "citation": "[src_001, ev_001]",
            }
        ],
    }
    metrics = score_result(item, "standard", result)
    assert metrics["fact_recall"] == 1.0
    assert metrics["preferred_source_hit"] == 1.0
    assert metrics["citation_integrity"] == 1.0
    assert metrics["answer_readiness_score"] == 100.0


def test_hybrid_scoring_counts_traceable_search_snippet_without_inflating_evidence() -> None:
    item = {
        "assertions": [{"label": "fact", "patterns": [r"correct fact"]}],
        "preferred_domains": ["example.org"],
    }
    result = {
        "sources": [],
        "evidence": [],
        "search_snippets": [
            {
                "snippet_id": "search_001",
                "title": "Primary result",
                "text": "The correct fact is present.",
                "url": "https://docs.example.org/fact",
                "domain": "docs.example.org",
                "verification": "snippet_only",
                "citation": "[search_001]",
                "injection_risk": "low",
            }
        ],
    }
    metrics = score_result(item, "adaptive_hybrid", result)
    assert metrics["fact_recall"] == 1.0
    assert metrics["preferred_source_hit"] == 1.0
    assert metrics["snippet_traceability"] == 1.0
    assert metrics["citation_integrity"] == 0.0


def test_preferred_source_requires_a_gold_fact_from_that_domain() -> None:
    item = {
        "assertions": [{"label": "fact", "patterns": [r"correct fact"]}],
        "preferred_domains": ["primary.example"],
    }
    result = {
        "sources": [
            {
                "source_id": "src_primary",
                "url": "https://primary.example/unrelated",
                "domain": "primary.example",
            },
            {
                "source_id": "src_secondary",
                "url": "https://secondary.example/fact",
                "domain": "secondary.example",
            },
        ],
        "evidence": [
            {
                "evidence_id": "ev_primary",
                "source_id": "src_primary",
                "text": "This primary-source passage is unrelated.",
                "start_offset": 0,
                "end_offset": 41,
                "citation": "[src_primary, ev_primary]",
            },
            {
                "evidence_id": "ev_secondary",
                "source_id": "src_secondary",
                "text": "The correct fact is only in the secondary source.",
                "start_offset": 0,
                "end_offset": 49,
                "citation": "[src_secondary, ev_secondary]",
            },
        ],
    }

    metrics = score_result(item, "adaptive_hybrid", result)

    assert metrics["fact_recall"] == 1.0
    assert metrics["preferred_source_hit"] == 0.0


def test_raw_preferred_source_requires_a_gold_fact_from_that_source() -> None:
    item = {
        "assertions": [{"label": "fact", "patterns": [r"correct fact"]}],
        "preferred_domains": ["primary.example"],
    }
    result = {
        "sources": [
            {
                "title": "Primary but unrelated",
                "snippet": "No benchmark assertion appears here.",
                "url": "https://primary.example/unrelated",
            },
            {
                "title": "Secondary result",
                "snippet": "The correct fact is present here.",
                "url": "https://secondary.example/fact",
            },
        ]
    }

    metrics = score_result(item, "raw_searxng", result)

    assert metrics["fact_recall"] == 1.0
    assert metrics["preferred_source_hit"] == 0.0


def test_wal_concurrency_assertion_rejects_explicit_negation() -> None:
    questions = json.loads(
        Path("benchmarks/answer_quality_questions.json").read_text(encoding="utf-8")
    )
    wal_item = next(item for item in questions if item["id"] == "aq04")
    result = {
        "sources": [
            {
                "title": "Incorrect statement",
                "snippet": "A writer and multiple readers cannot operate concurrently.",
                "url": "https://example.org/incorrect",
            }
        ]
    }
    metrics = score_result(wal_item, "raw_searxng", result)
    concurrency = next(
        row for row in metrics["assertions"] if row["label"].startswith("readers and writer")
    )
    assert concurrency["hit"] is False
