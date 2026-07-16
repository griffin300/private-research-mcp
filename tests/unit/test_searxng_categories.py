import httpx
import pytest
import respx

from app.search.searxng import SearxngBackend, SearxngError, _categories_for_query


def test_searxng_adds_relevant_verticals_without_dropping_general() -> None:
    assert _categories_for_query("Python HTTP API release") == "general"
    assert _categories_for_query("Python package install traceback") == "general,it"
    assert _categories_for_query("peer-reviewed science paper") == "general,science"
    assert _categories_for_query("breaking election news today") == "general,news"
    assert _categories_for_query("ordinary factual question") == "general"


@respx.mock
async def test_searxng_retries_one_whole_degraded_empty_response() -> None:
    route = respx.get("http://searxng:8080/search").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "results": [],
                    "unresponsive_engines": [["brave", "Suspended: too many requests"]],
                },
            ),
            httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.com/recovered",
                            "title": "Recovered result",
                            "content": "Exact query result after aggregate recovery.",
                            "engine": "example",
                        }
                    ]
                },
            ),
        ]
    )
    backend = SearxngBackend("http://searxng:8080", 30, recovery_delay_seconds=0)

    results = await backend.search(
        "exact launch query", language="en", recency_days=None, limit=10
    )

    assert route.call_count == 2
    assert [call.request.url.params["q"] for call in route.calls] == [
        "exact launch query",
        "exact launch query",
    ]
    assert results[0].url == "https://example.com/recovered"


@respx.mock
async def test_searxng_does_not_retry_a_healthy_empty_response() -> None:
    route = respx.get("http://searxng:8080/search").mock(
        return_value=httpx.Response(200, json={"results": [], "unresponsive_engines": []})
    )
    backend = SearxngBackend("http://searxng:8080", 30, recovery_delay_seconds=0)

    results = await backend.search("no matching documents", language="en", recency_days=None, limit=5)

    assert route.call_count == 1
    assert results == []


@respx.mock
async def test_searxng_retries_one_whole_transport_failure() -> None:
    request = httpx.Request("GET", "http://searxng:8080/search")
    route = respx.get("http://searxng:8080/search").mock(
        side_effect=[
            httpx.ConnectError("temporary failure", request=request),
            httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.com/recovered",
                            "title": "Recovered result",
                            "content": "Recovered without direct egress.",
                        }
                    ]
                },
            ),
        ]
    )
    backend = SearxngBackend("http://searxng:8080", 30, recovery_delay_seconds=0)

    results = await backend.search("exact query", language="en", recency_days=None, limit=5)

    assert route.call_count == 2
    assert len(results) == 1


@respx.mock
async def test_searxng_does_not_retry_a_deterministic_client_error() -> None:
    route = respx.get("http://searxng:8080/search").mock(return_value=httpx.Response(400))
    backend = SearxngBackend("http://searxng:8080", 30, recovery_delay_seconds=0)

    with pytest.raises(SearxngError):
        await backend.search("invalid request", language="en", recency_days=None, limit=5)

    assert route.call_count == 1
