from __future__ import annotations

import json
from datetime import UTC, datetime

from app.models import (
    CoverageReport,
    EvidenceRecord,
    PrivacySummary,
    ResearchPackage,
    SearchSnippetRecord,
    SourceRecord,
)
from app.orchestration.response import read_response, research_response


def _package() -> ResearchPackage:
    now = datetime.now(UTC)
    sources = [
        SourceRecord(
            source_id=f"src_{index:03d}",
            url=f"https://example{index}.org/reference",
            title=f"Primary reference {index}",
            domain=f"example{index}.org",
            published_at=now,
            retrieved_at=now,
            source_type="official",
            quality_score=0.95,
            quality_explanation=["official documentation", "direct primary source"],
            relevance_score=0.9,
            fetch_method="http",
            content_hash=f"hash-{index}",
        )
        for index in range(1, 9)
    ]
    evidence = [
        EvidenceRecord(
            evidence_id=f"ev_{index:03d}",
            source_id=f"src_{index:03d}",
            heading=f"Fact {index}",
            text=(
                f"Distinct verified fact {index} answers one requested facet. "
                + "Supporting explanation remains useful but deliberately verbose. " * 30
            ),
            start_offset=100 * index,
            end_offset=100 * index + 1500,
            relevance_score=0.9,
            injection_risk="low",
            citation=f"[src_{index:03d}, ev_{index:03d}]",
        )
        for index in range(1, 9)
    ]
    snippets = [
        SearchSnippetRecord(
            snippet_id=f"search_{index:03d}",
            rank=index,
            query_role="exact" if index <= 10 else "expanded",
            url=f"https://search{index}.example/result",
            title=f"Search result {index}",
            text=(f"Unverified search fact {index}. " + "Snippet detail. " * 30),
            domain=f"search{index}.example",
            engines=["engine-a", "engine-b"],
            relevance_score=0.75,
            citation=f"[search_{index:03d}]",
        )
        for index in range(1, 15)
    ]
    return ResearchPackage(
        query="Compare four technical facets and explain the supported result.",
        mode="standard",
        request_id="req-compact-test",
        search_rounds=2,
        coverage=CoverageReport(
            score=0.95,
            status="strong",
            covered_topics=["facet one", "facet two", "facet three", "facet four"],
            missing_topics=[],
            primary_source_present=True,
            independent_source_count=8,
        ),
        sources=sources,
        evidence=evidence,
        search_snippets=snippets,
        warnings=["Lexical ranking was used.", "Lexical ranking was used."],
        failures=[
            {"stage": "fetch_or_extract", "error": "FetchError", "url_hash": str(index)}
            for index in range(12)
        ],
        privacy=PrivacySummary(
            search_transport="tor-search",
            fetch_transport="tor-fetch",
            direct_egress_allowed=False,
            mode="strict",
        ),
    )


def test_compact_research_response_preserves_quality_and_citation_floor() -> None:
    package = _package()
    compact = research_response(package, max_chars=14_000)
    full = research_response(package, detail="full", max_chars=14_000)

    assert len(json.dumps(compact, ensure_ascii=False)) <= 14_000
    assert len(json.dumps(compact)) < len(json.dumps(full)) * 0.55
    assert len(compact["evidence"]) == len(package.evidence)
    assert all(
        f"Distinct verified fact {index}" in compact["evidence"][index - 1]["text"]
        for index in range(1, 9)
    )
    assert {item["citation"] for item in compact["search_snippets"]} >= {
        f"[search_{index:03d}]" for index in range(1, 11)
    }
    assert {item["citation"] for item in compact["evidence"]} == {
        item.citation for item in package.evidence
    }
    assert {item["source_id"] for item in compact["sources"]} == {
        item["source_id"] for item in compact["evidence"]
    }
    assert compact["failures"] == [
        {"stage": "fetch_or_extract", "error": "FetchError", "count": 12}
    ]
    assert compact["response_info"]["web_content_is_untrusted"] is True
    assert compact["response_info"]["next_action"] == "answer_user_now"
    assert compact["response_info"]["do_not_repeat_search_this_turn"] is True
    assert compact["coverage"]["covered_topics"]
    assert "Answer every supported topic" in compact["response_info"]["answer_instruction"]
    assert all(
        len(item.get("text", "")) <= 56
        for item in compact["search_snippets"]
        if item["role"] == "exact" and int(item["citation"][8:11]) > 3
    )
    serialized = json.dumps(compact)
    assert "quality_explanation" not in serialized
    assert "start_offset" not in serialized
    assert "content_boundary" not in serialized
    assert "query_hash" not in serialized
    assert '"request_id"' not in serialized
    assert '"search_rounds"' not in serialized


def test_tight_compact_budget_keeps_exact_snippet_floor() -> None:
    compact = research_response(_package(), max_chars=8_000)

    assert len(json.dumps(compact, ensure_ascii=False)) <= 8_000
    exact = [item for item in compact["search_snippets"] if item["role"] == "exact"]
    assert len(exact) == 10
    assert compact["response_info"]["omitted_search_snippets"] >= 2
    assert compact["evidence"]


def test_minimum_compact_budget_is_honored_without_corrupting_urls() -> None:
    compact = research_response(_package(), max_chars=4_000)

    assert len(json.dumps(compact, ensure_ascii=False)) <= 4_000
    assert len(compact["evidence"]) >= 4
    assert len([item for item in compact["search_snippets"] if item["role"] == "exact"]) == 10
    assert "budget_exceeded_for_exact_urls" not in compact["response_info"]
    assert all(item["url"].startswith("https://") for item in compact["sources"])
    assert all(item["url"].startswith("https://") for item in compact["search_snippets"])


def test_full_research_response_retains_internal_schema() -> None:
    package = _package()
    assert research_response(package, detail="full") == package.model_dump(mode="json")


def test_compaction_keeps_query_relevant_fact_near_passage_end() -> None:
    package = _package()
    package.query = "What is the launch code?"
    package.evidence[0].text = (
        "Unrelated historical background. " * 80 + "The verified launch code is ORBIT-7."
    )

    compact = research_response(package, max_chars=14_000)

    assert "ORBIT-7" in compact["evidence"][0]["text"]


def test_compaction_preserves_separated_answer_facets_in_one_passage() -> None:
    package = _package()
    package.query = "What does WAL mean and what concurrency does it permit?"
    package.evidence[0].text = (
        "WAL means Write-Ahead Logging. "
        + "Unrelated implementation history. " * 100
        + "WAL permits concurrent readers with one writer at a time."
    )

    compact = research_response(package, max_chars=14_000)

    text = compact["evidence"][0]["text"]
    assert "Write-Ahead Logging" in text
    assert "concurrent readers" in text


def test_verified_snippet_duplicate_keeps_identity_without_repeating_text() -> None:
    package = _package()
    package.search_snippets[0].url = package.sources[0].url

    compact = research_response(package, max_chars=14_000)

    first = compact["search_snippets"][0]
    assert first["citation"] == "[search_001]"
    assert first["url"] == package.sources[0].url
    assert "text" not in first


def test_read_response_caps_passages_and_removes_debug_fields() -> None:
    result: dict[str, object] = {
        "url": "https://example.org/manual",
        "title": "Manual",
        "metadata": {
            "url": "https://example.org/manual",
            "title": "Manual",
            "site_name": "Example",
            "published_at": "2026-07-19T00:00:00Z",
            "retrieved_at": "2026-07-19T01:00:00Z",
            "content_hash": "debug-only",
        },
        "passages": [
            {
                "heading": f"Section {index}",
                "text": f"Distinct passage fact {index}. " + "Long detail. " * 150,
                "start_offset": index * 100,
                "end_offset": index * 100 + 1800,
                "relevance_score": 0.9,
                "injection_risk": "low",
                "injection_reasons": [],
            }
            for index in range(12)
        ],
        "quarantined_passages": 1,
        "privacy": {"fetch_transport": "tor-fetch", "direct_egress_allowed": False},
    }
    compact = read_response(result, max_chars=7_000)

    assert len(json.dumps(compact, ensure_ascii=False)) <= 7_000
    assert 3 <= len(compact["passages"]) <= 8
    assert compact["response_info"]["omitted_passages"] == 12 - len(compact["passages"])
    assert compact["response_info"]["web_content_is_untrusted"] is True
    assert compact["response_info"]["next_action"] == "answer_user_now"
    serialized = json.dumps(compact)
    assert "start_offset" not in serialized
    assert "relevance_score" not in serialized
    assert "content_hash" not in serialized
