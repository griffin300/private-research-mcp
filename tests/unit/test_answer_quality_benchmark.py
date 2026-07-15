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
