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
    context, citations = build_context(
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
    assert context.startswith("[src_001]")
    assert citations == {"[src_001]"}


def test_citations_without_gold_facts_do_not_earn_quality_points() -> None:
    item = {"assertions": [{"label": "expected", "patterns": [r"correct fact"]}]}
    metrics = score_answer(item, "A different claim [src_001].", {"[src_001]"})
    assert metrics["citation_precision"] == 1.0
    assert metrics["answer_fact_recall"] == 0.0
    assert metrics["answer_quality_score"] == 0.0
