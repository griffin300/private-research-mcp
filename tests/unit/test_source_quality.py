from app.models import Passage, SearchResult
from app.orchestration.pipeline import _absolute_source_relevance
from app.ranking.source_quality import score_search_result, source_type


def test_no_anchor_query_does_not_receive_an_automatic_anchor_bonus() -> None:
    result = SearchResult(
        url="https://weather.example/forecast",
        title="Unrelated weather forecast",
        snippet="Rain and wind are expected tomorrow.",
        rank=1,
        engine="fixture",
        engines=["fixture", "second_fixture"],
        search_score=1.0,
    )

    assert score_search_result("database transaction isolation", result) < 0.30


def test_lookalike_github_hostname_is_not_a_source_repository() -> None:
    assert source_type("https://evilgithub.com/owner/repository") == "web_page"


def test_off_topic_page_cannot_inherit_relevance_from_search_prior() -> None:
    result = SearchResult(
        url="https://docs.example/unrelated",
        title="Promising search title",
        snippet="database transaction isolation",
        preliminary_score=1.0,
    )
    passages = [
        Passage(
            text="Tomorrow will be rainy with strong coastal wind.",
            start_offset=0,
            end_offset=48,
            relevance_score=1.0,
        )
    ]

    assert _absolute_source_relevance(
        result, ["database transaction isolation"], passages
    ) == 0.0


def test_page_missing_critical_identifier_has_zero_absolute_relevance() -> None:
    result = SearchResult(
        url="https://docs.python.org/release",
        title="Python release",
        preliminary_score=1.0,
    )
    passages = [
        Passage(
            text="Python releases include security and compatibility fixes.",
            start_offset=0,
            end_offset=57,
            relevance_score=1.0,
        )
    ]

    assert _absolute_source_relevance(
        result, ["Python 3.12.0 release date"], passages
    ) == 0.0
