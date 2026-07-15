from benchmarks.synthesize_answers import build_context, score_answer


def test_answer_scoring_rewards_gold_facts_with_valid_citations() -> None:
    item = {
        "assertions": [
            {"label": "transport", "patterns": [r"streamable\s+http"]},
            {"label": "production", "patterns": [r"production"]},
        ]
    }
    answer = "Streamable HTTP is recommended for production deployments. [src_001, ev_001]"
    metrics = score_answer(item, answer, {"[src_001, ev_001]"})
    assert metrics["answer_fact_recall"] == 1.0
    assert metrics["grounded_fact_recall"] == 1.0
    assert metrics["citation_precision"] == 1.0
    assert metrics["claim_citation_coverage"] == 1.0
    assert metrics["answer_quality_score"] == 100.0


def test_raw_context_assigns_stable_citations() -> None:
    context = build_context(
        {
            "mode": "raw_searxng",
            "result": {
                "sources": [
                    {
                        "title": "Official result",
                        "snippet": "Supporting fact",
                        "url": "https://example.org/fact",
                    }
                ]
            },
        }
    )
    assert context.text.startswith("[S1]")
    assert context.valid_citations == {"[S1]"}
    assert context.citation_map == {"[S1]": "https://example.org/fact"}


def test_citations_without_gold_facts_do_not_earn_quality_points() -> None:
    item = {"assertions": [{"label": "expected", "patterns": [r"correct fact"]}]}
    metrics = score_answer(item, "A different claim [src_001].", {"[src_001]"})
    assert metrics["citation_precision"] == 1.0
    assert metrics["answer_fact_recall"] == 0.0
    assert metrics["answer_quality_score"] == 0.0


def test_research_context_uses_compact_citations_and_a_canonical_map() -> None:
    context = build_context(
        {
            "mode": "quick",
            "result": {
                "sources": [{"source_id": "src_001", "title": "Official documentation"}],
                "evidence": [
                    {
                        "source_id": "src_001",
                        "evidence_id": "ev_001",
                        "citation": "[src_001, ev_001]",
                        "text": "A concise supported fact.",
                    }
                ],
            },
        }
    )
    assert context.text.startswith("[E1]")
    assert context.valid_citations == {"[E1]"}
    assert context.citation_map == {"[E1]": "[src_001, ev_001]"}


def test_explicit_abstention_cannot_receive_fact_credit() -> None:
    item = {"assertions": [{"label": "transport", "patterns": [r"streamable\s+http"]}]}
    metrics = score_answer(
        item,
        "The context does not specify whether Streamable HTTP is recommended [E1].",
        {"[E1]"},
    )
    assert metrics["abstained"] is True
    assert metrics["answer_fact_recall"] == 0.0
    assert metrics["answer_quality_score"] == 0.0


def test_short_numeric_bullet_can_be_grounded() -> None:
    item = {"assertions": [{"label": "block", "patterns": [r"10\.0\.0\.0/8"]}]}
    metrics = score_answer(item, "- 10.0.0.0/8 [E1]", {"[E1]"})
    assert metrics["grounded_fact_recall"] == 1.0
