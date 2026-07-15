import asyncio
from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.extract.extractor import PageExtractor
from app.fetch.browser_fetcher import BrowserFetcher
from app.fetch.http_fetcher import FetchError
from app.models import FetchResult, SearchMode, SearchResult
from app.orchestration.pipeline import ResearchPipeline
from app.storage.cache import Cache
from app.storage.database import Database


class FakeBackend:
    def __init__(self) -> None:
        self.calls = 0

    async def search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        self.calls += 1
        return [
            SearchResult(
                url=f"https://example.com/{abs(hash(query))}",
                title=f"Official {query}",
                snippet="MCP research evidence transport",
                engine="fixture",
            )
        ]

    async def health(self) -> dict[str, object]:
        return {"status": "healthy"}


class RecoveringBackend(FakeBackend):
    async def search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        self.calls += 1
        if self.calls <= 2:
            return []
        return [
            SearchResult(
                url="https://example.com/recovered",
                title="Recovered official result",
                snippet="Recovered evidence",
                engine="fixture",
            )
        ]


class ConcurrentBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.maximum_active = 0

    async def search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        self.calls += 1
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return [
            SearchResult(
                url=f"https://example.com/{query}",
                title=query,
                snippet="evidence",
                engine="fixture",
            )
        ]


class FakeFetcher:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, url: str) -> FetchResult:
        self.calls += 1
        body = "<html><head><title>Official evidence</title></head><body><main><h1>MCP transport</h1><p>Streamable HTTP is a supported MCP transport with structured evidence and exact citations for research systems.</p><p>A second independent paragraph explains privacy isolation through separate search and destination fetch gateways.</p></main></body></html>"
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=body,
            retrieved_at=datetime.now(UTC),
        )


class RobotsDenyFetcher:
    async def fetch(self, url: str) -> FetchResult:
        assert url.endswith("/robots.txt")
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/plain",
            body="User-agent: *\nDisallow: /",
            retrieved_at=datetime.now(UTC),
        )


@pytest.mark.integration
async def test_full_pipeline_returns_cited_evidence(tmp_path) -> None:
    settings = Settings(
        privacy_mode="development",
        direct_egress_allowed=False,
        database_path=tmp_path / "research.db",
        admin_host="127.0.0.1",
        mcp_host="127.0.0.1",
    )
    database = Database(settings.database_path)
    database.initialize()
    backend = FakeBackend()
    fetcher = FakeFetcher()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=backend,
        fetcher=fetcher,  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    result = await pipeline.search_web("MCP transport privacy", mode=SearchMode.QUICK)
    assert result.sources
    assert result.evidence
    assert result.evidence[0].citation.startswith("[src_")
    assert result.privacy.direct_egress_allowed is False
    assert not any(row[0] for row in [database.query_one("SELECT raw_query FROM requests")])
    assert database.query_one("SELECT count(*) FROM evidence_fts")[0] > 0

    first_backend_calls = backend.calls
    first_fetch_calls = fetcher.calls
    repeated = await pipeline.search_web("MCP transport privacy", mode=SearchMode.QUICK)
    assert repeated.evidence
    assert backend.calls == first_backend_calls
    assert fetcher.calls == first_fetch_calls


@pytest.mark.integration
async def test_deep_research_executes_multiple_distinct_rounds(tmp_path) -> None:
    settings = Settings(
        privacy_mode="development",
        database_path=tmp_path / "deep.db",
    )
    database = Database(settings.database_path)
    database.initialize()
    backend = FakeBackend()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=backend,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    result = await pipeline.deep_research("MCP transport and privacy", max_search_rounds=3)
    assert result.search_rounds == 3
    assert backend.calls >= 3


@pytest.mark.integration
async def test_deep_query_budget_scales_to_requested_sources(tmp_path) -> None:
    settings = Settings(privacy_mode="development", database_path=tmp_path / "scaled-deep.db")
    database = Database(settings.database_path)
    database.initialize()
    backend = FakeBackend()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=backend,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    result = await pipeline.search_web("MCP transport privacy", mode=SearchMode.DEEP, max_sources=3)
    assert result.search_rounds == 3
    assert backend.calls <= 6


@pytest.mark.integration
async def test_empty_search_results_are_retried_instead_of_cached(tmp_path) -> None:
    settings = Settings(privacy_mode="development", database_path=tmp_path / "empty-cache.db")
    database = Database(settings.database_path)
    database.initialize()
    backend = RecoveringBackend()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=backend,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    first = await pipeline._search_cached(
        "On what date was the historical release?", language="en", recency_days=None, limit=5
    )
    second = await pipeline._search_cached(
        "On what date was the historical release?", language="en", recency_days=None, limit=5
    )
    third = await pipeline._search_cached(
        "On what date was the historical release?", language="en", recency_days=None, limit=5
    )
    assert not first
    assert second
    assert third
    assert backend.calls == 3


@pytest.mark.integration
async def test_strict_search_cache_misses_are_serialized(tmp_path) -> None:
    settings = Settings(
        privacy_mode="strict",
        database_path=tmp_path / "serialized-search.db",
        search_min_interval_seconds=0,
    )
    database = Database(settings.database_path)
    database.initialize()
    backend = ConcurrentBackend()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=backend,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    results, failures = await pipeline._search_round(
        ["one", "two", "three"], language="en", recency_days=None, limit=3
    )
    assert len(results) == 3
    assert not failures
    assert backend.maximum_active == 1


@pytest.mark.integration
async def test_read_url_honors_robots_disallow(tmp_path) -> None:
    settings = Settings(privacy_mode="development", database_path=tmp_path / "robots.db")
    database = Database(settings.database_path)
    database.initialize()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=FakeBackend(),
        fetcher=RobotsDenyFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    with pytest.raises(FetchError, match="robots"):
        await pipeline.read_url("https://example.com/private")
