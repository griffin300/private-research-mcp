from datetime import UTC, datetime

import httpx
import pytest

from app.fetch.http_fetcher import FetchError, HttpFetcher, _is_transient
from app.fetch.policies import FetchPolicy
from app.models import FetchResult


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError("status", request=request, response=response)


def test_only_transient_fetch_failures_are_retried() -> None:
    assert _is_transient(_status_error(503))
    assert _is_transient(httpx.ConnectTimeout("timeout"))
    assert not _is_transient(_status_error(404))
    assert not _is_transient(FetchError("unsupported content type"))


@pytest.mark.asyncio
async def test_deterministic_errors_do_not_open_domain_circuit(monkeypatch) -> None:
    fetcher = HttpFetcher(
        policy=FetchPolicy(max_response_bytes=1024, max_redirects=0, timeout_seconds=1, retries=0),
        proxy_url=None,
        strict_privacy=False,
    )
    calls = 0

    async def fake_fetch_once(client: httpx.AsyncClient, url: str) -> FetchResult:
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise _status_error(404)
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/plain",
            body="valid response",
            retrieved_at=datetime.now(UTC),
        )

    monkeypatch.setattr(fetcher, "_fetch_once", fake_fetch_once)
    for _ in range(3):
        with pytest.raises(FetchError):
            await fetcher.fetch("https://example.com/missing")
    result = await fetcher.fetch("https://example.com/valid")
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_request_session_reuses_client_then_closes_it(monkeypatch) -> None:
    fetcher = HttpFetcher(
        policy=FetchPolicy(max_response_bytes=1024, max_redirects=0, timeout_seconds=1, retries=0),
        proxy_url=None,
        strict_privacy=False,
    )
    clients: list[httpx.AsyncClient] = []

    async def fake_fetch_once(client: httpx.AsyncClient, url: str) -> FetchResult:
        clients.append(client)
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/plain",
            body="valid response",
            retrieved_at=datetime.now(UTC),
        )

    monkeypatch.setattr(fetcher, "_fetch_once", fake_fetch_once)
    async with fetcher.session():
        await fetcher.fetch("https://example.com/robots.txt")
        await fetcher.fetch("https://example.com/reference")

    assert clients[0] is clients[1]
    assert clients[0].is_closed

    async with fetcher.session():
        await fetcher.fetch("https://example.com/another-reference")

    assert clients[2] is not clients[0]
    assert clients[2].is_closed
