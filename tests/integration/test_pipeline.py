import asyncio
from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.extract.extractor import PageExtractor
from app.fetch.browser_fetcher import BrowserFetcher
from app.fetch.http_fetcher import FetchError
from app.models import FetchResult, SearchMode, SearchResult
from app.orchestration.pipeline import ResearchPipeline
from app.search.query_expansion import QueryPlan
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


class RecordingBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[str] = []

    async def search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        self.calls += 1
        self.queries.append(query)
        return [
            SearchResult(
                url=f"https://facet-{index}.example/{abs(hash(query))}",
                title=f"Focused evidence {query}",
                snippet=f"Primary documentation answering {query}",
                rank=index,
                engine="fixture",
            )
            for index in range(1, min(limit, 3) + 1)
        ]


class FacetFactBackend(FakeBackend):
    async def search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        self.calls += 1
        lowered = query.casefold()
        if "sqlite" in lowered:
            host, fact = (
                "sqlite.example",
                "SQLite WAL concurrent readers continue while one writer appends changes.",
            )
        elif "streamable" in lowered or "mcp" in lowered:
            host, fact = (
                "mcp.example",
                "MCP Streamable HTTP transport carries protocol messages over HTTP.",
            )
        elif "tor" in lowered:
            host, fact = (
                "tor.example",
                "Tor stream isolation destinations use separated proxy streams.",
            )
        else:
            return []
        return [
            SearchResult(
                url=f"https://{host}/fact",
                title=fact,
                snippet=fact,
                rank=1,
                engine="fixture",
            )
        ]


class FacetFactFetcher:
    async def fetch(self, url: str) -> FetchResult:
        if url.endswith("/robots.txt"):
            body, content_type = "User-agent: *\nAllow: /\n", "text/plain"
        elif "sqlite.example" in url:
            body, content_type = (
                "<main><h1>SQLite WAL concurrent readers</h1><p>SQLite WAL concurrent readers "
                "continue while one writer appends changes to the write-ahead log. This factual "
                "fixture provides enough independent text for extraction and citation.</p></main>",
                "text/html",
            )
        elif "mcp.example" in url:
            body, content_type = (
                "<main><h1>MCP Streamable HTTP transport</h1><p>MCP Streamable HTTP transport "
                "carries protocol messages over HTTP. This factual fixture provides enough "
                "independent text for extraction and citation.</p></main>",
                "text/html",
            )
        else:
            body, content_type = (
                "<main><h1>Tor stream isolation destinations</h1><p>Tor stream isolation "
                "destinations use separated proxy streams. This factual fixture provides enough "
                "independent text for extraction and citation.</p></main>",
                "text/html",
            )
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type=content_type,
            body=body,
            retrieved_at=datetime.now(UTC),
        )


class SlowBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.cancelled = 0

    async def search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        self.calls += 1
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        return []


class GateBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = 0

    async def search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        self.calls += 1
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        return [
            SearchResult(
                url="https://example.com/shared",
                title="Shared result",
                snippet="Shared evidence",
                engine="fixture",
            )
        ]


class RobotsRulesFetcher:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, url: str) -> FetchResult:
        self.calls += 1
        await asyncio.sleep(0.01)
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/plain",
            body="User-agent: *\nDisallow: /private\n",
            retrieved_at=datetime.now(UTC),
        )


class OrderedBackend(FakeBackend):
    def __init__(self, exact_query: str) -> None:
        super().__init__()
        self.exact_query = exact_query
        self.limits: list[tuple[str, int]] = []

    async def search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        self.calls += 1
        self.limits.append((query, limit))
        if query == self.exact_query:
            return [
                SearchResult(
                    url=f"https://exact-{index}.example/result",
                    title=f"Exact result {index}",
                    snippet="" if index == 4 else f"Exact evidence {index}",
                    engine="fixture",
                )
                for index in range(1, limit + 1)
            ]
        return [
            SearchResult(
                url=f"https://expanded.example/{abs(hash(query))}",
                title="Expanded result",
                snippet="Expanded evidence",
                engine="fixture",
            )
        ]


class AlwaysFailFetcher:
    async def fetch(self, url: str) -> FetchResult:
        raise FetchError("fixture failure")


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


class AdaptiveFacetFetcher:
    def __init__(self) -> None:
        self.page_urls: list[str] = []

    async def fetch(self, url: str) -> FetchResult:
        if url.endswith("/robots.txt"):
            body, content_type = "User-agent: *\nAllow: /\n", "text/plain"
        else:
            self.page_urls.append(url)
            if "python-primary" in url:
                raise FetchError("primary fixture failure")
            if "python-backup" in url:
                fact = (
                    "Python contextlib.AsyncExitStack manages asynchronous exit callbacks "
                    "and cleanup resources in a stack."
                )
            elif "sqlite-primary" in url:
                fact = "SQLite WAL permits concurrent readers while a writer appends changes."
            else:
                fact = "MCP Streamable HTTP transport carries protocol messages over HTTP."
            body = f"<main><h1>{fact}</h1><p>{fact} Verified fixture detail.</p></main>"
            content_type = "text/html"
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type=content_type,
            body=body,
            retrieved_at=datetime.now(UTC),
        )


class BrowserBudgetFetcher:
    async def fetch(self, url: str) -> FetchResult:
        if url.endswith("/robots.txt"):
            body, content_type = "User-agent: *\nAllow: /\n", "text/plain"
        elif "needs-browser" in url:
            raise FetchError("HTTP extraction path failed")
        else:
            body = (
                "<main><p>MCP Streamable HTTP transport provides enough factual text "
                "for deterministic extraction and ranking.</p></main>"
            )
            content_type = "text/html"
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type=content_type,
            body=body,
            retrieved_at=datetime.now(UTC),
        )


class SuccessfulBrowser:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, url: str) -> FetchResult:
        self.calls += 1
        body = (
            "<main><p>MCP Streamable HTTP transport browser fallback returns sufficient "
            "clean factual content for extraction.</p></main>"
        )
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=body,
            method="browser",
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
    assert result.search_rounds == 4
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
async def test_identical_concurrent_searches_share_one_backend_call(tmp_path) -> None:
    settings = Settings(
        privacy_mode="development",
        database_path=tmp_path / "singleflight-search.db",
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
    first, second = await asyncio.gather(
        pipeline._search_cached("same query", language="en", recency_days=None, limit=3),
        pipeline._search_cached("same query", language="en", recency_days=None, limit=3),
    )
    assert first and second
    assert backend.calls == 1


@pytest.mark.integration
async def test_canceling_one_singleflight_waiter_does_not_cancel_the_other(tmp_path) -> None:
    settings = Settings(
        privacy_mode="development",
        database_path=tmp_path / "singleflight-cancel.db",
        search_min_interval_seconds=0,
    )
    database = Database(settings.database_path)
    database.initialize()
    backend = GateBackend()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=backend,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    first = asyncio.create_task(
        pipeline._search_cached("same query", language="en", recency_days=None, limit=3)
    )
    second = asyncio.create_task(
        pipeline._search_cached("same query", language="en", recency_days=None, limit=3)
    )
    await backend.started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    backend.release.set()
    assert await second
    assert backend.calls == 1
    assert backend.cancelled == 0
    assert not pipeline._search_inflight


@pytest.mark.integration
async def test_new_singleflight_request_does_not_join_canceling_flight(tmp_path) -> None:
    settings = Settings(privacy_mode="development", database_path=tmp_path / "flight-race.db")
    database = Database(settings.database_path)
    database.initialize()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=FakeBackend(),
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    registry = {}
    started = asyncio.Event()
    cancellation_seen = asyncio.Event()
    allow_cleanup = asyncio.Event()
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls > 1:
            return "fresh"
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellation_seen.set()
            await allow_cleanup.wait()
            raise

    first = asyncio.create_task(pipeline._coalesce(registry, "key", operation))
    await started.wait()
    first.cancel()
    await cancellation_seen.wait()
    second = asyncio.create_task(pipeline._coalesce(registry, "key", operation))
    assert await asyncio.wait_for(second, 1) == "fresh"
    allow_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert calls == 2
    assert not registry


@pytest.mark.integration
async def test_explicit_query_batch_uses_one_bounded_facet_pipeline(tmp_path) -> None:
    facets = [
        "What is MCP Streamable HTTP?",
        "How does SQLite WAL mode work?",
        "What does Tor stream isolation do?",
    ]
    question = "[" + ",".join(f'"{facet}"' for facet in facets) + "]"
    settings = Settings(privacy_mode="development", database_path=tmp_path / "compound.db")
    database = Database(settings.database_path)
    database.initialize()
    backend = RecordingBackend()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=backend,
        fetcher=AlwaysFailFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    result = await pipeline.search_web(question, mode=SearchMode.DEEP, max_sources=3)
    assert question not in backend.queries
    assert backend.queries[:3] == facets
    assert backend.calls <= 6
    assert [item.query_role for item in result.search_snippets[:3]] == ["exact"] * 3
    assert any("focused facets" in warning for warning in result.warnings)


@pytest.mark.integration
async def test_oversized_query_batch_reports_unprocessed_facets(tmp_path) -> None:
    facets = [f"Focused research question number {index}" for index in range(1, 8)]
    question = "[" + ",".join(f'"{facet}"' for facet in facets) + "]"
    settings = Settings(privacy_mode="development", database_path=tmp_path / "large-batch.db")
    database = Database(settings.database_path)
    database.initialize()
    backend = RecordingBackend()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=backend,
        fetcher=AlwaysFailFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    result = await pipeline.search_web(question, mode=SearchMode.STANDARD, max_sources=1)
    assert backend.queries[:6] == facets[:6]
    assert facets[6] not in backend.queries
    assert any("1 additional question" in warning for warning in result.warnings)
    assert any("facet limit" in item for item in result.unresolved_questions)


@pytest.mark.integration
async def test_compound_retrieval_backfills_failed_technical_facet_within_cap(tmp_path) -> None:
    facets = [
        "Python contextlib.AsyncExitStack",
        "SQLite WAL concurrent readers",
        "MCP Streamable HTTP transport",
    ]
    candidates = [
        SearchResult(
            url="https://python-primary.example/page",
            canonical_url="https://python-primary.example/page",
            title="Python contextlib.AsyncExitStack",
            snippet="Official asynchronous exit stack documentation",
            domain="python-primary.example",
        ),
        SearchResult(
            url="https://sqlite-primary.example/page",
            canonical_url="https://sqlite-primary.example/page",
            title="SQLite WAL concurrent readers",
            snippet="Write-ahead logging documentation",
            domain="sqlite-primary.example",
        ),
        SearchResult(
            url="https://mcp-primary.example/page",
            canonical_url="https://mcp-primary.example/page",
            title="MCP Streamable HTTP transport",
            snippet="Protocol specification",
            domain="mcp-primary.example",
        ),
        SearchResult(
            url="https://python-backup.example/page",
            canonical_url="https://python-backup.example/page",
            title="Python contextlib.AsyncExitStack reference",
            snippet="Async exit stack cleanup callbacks",
            domain="python-backup.example",
        ),
    ]
    settings = Settings(privacy_mode="development", database_path=tmp_path / "backfill.db")
    database = Database(settings.database_path)
    database.initialize()
    fetcher = AdaptiveFacetFetcher()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=FakeBackend(),
        fetcher=fetcher,  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    failures: list[dict[str, str]] = []
    ranked, attempts = await pipeline._retrieve(
        "compound fixture",
        QueryPlan("compound fixture", facets, facets, False),
        candidates,
        failures,
        browser_budget=0,
        relevance_queries=facets,
        deadline_at=None,
        attempt_limit=4,
        preferred_by_query=dict(zip(facets, candidates[:3], strict=True)),
    )
    retained_text = " ".join(
        passage.text for _, passages in ranked for passage in passages
    ).casefold()
    assert attempts == 4
    assert len(fetcher.page_urls) == 4
    assert all(term in retained_text for term in ("asyncexitstack", "sqlite", "streamable"))
    assert len(ranked) == 3


@pytest.mark.integration
async def test_browser_budget_is_claimed_only_after_http_failure(tmp_path) -> None:
    settings = Settings(
        privacy_mode="development",
        database_path=tmp_path / "browser-budget.db",
        enable_browser=True,
    )
    database = Database(settings.database_path)
    database.initialize()
    browser = SuccessfulBrowser()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=FakeBackend(),
        fetcher=BrowserBudgetFetcher(),  # type: ignore[arg-type]
        browser=browser,  # type: ignore[arg-type]
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    candidates = [
        SearchResult(
            url="https://http-success.example/page",
            canonical_url="https://http-success.example/page",
            title="MCP Streamable HTTP transport",
            domain="http-success.example",
        ),
        SearchResult(
            url="https://needs-browser.example/page",
            canonical_url="https://needs-browser.example/page",
            title="MCP Streamable HTTP transport browser source",
            domain="needs-browser.example",
        ),
    ]
    ranked, attempts = await pipeline._retrieve(
        "MCP Streamable HTTP transport",
        QueryPlan(
            "MCP Streamable HTTP transport",
            ["MCP Streamable HTTP transport"],
            ["MCP Streamable HTTP transport"],
            False,
        ),
        candidates,
        [],
        browser_budget=1,
        relevance_queries=["MCP Streamable HTTP transport"],
        deadline_at=None,
        attempt_limit=2,
    )
    assert attempts == 2
    assert len(ranked) == 2
    assert browser.calls == 1
    assert any(source.fetch_method == "browser" for source, _ in ranked)


@pytest.mark.integration
async def test_compound_pipeline_retains_cited_facts_for_every_facet(tmp_path) -> None:
    facets = [
        "SQLite WAL concurrent readers",
        "MCP Streamable HTTP transport",
        "Tor stream isolation destinations",
    ]
    question = "[" + ",".join(f'"{facet}"' for facet in facets) + "]"
    settings = Settings(privacy_mode="development", database_path=tmp_path / "compound-facts.db")
    database = Database(settings.database_path)
    database.initialize()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=FacetFactBackend(),
        fetcher=FacetFactFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    result = await pipeline.search_web(question, mode=SearchMode.STANDARD, max_sources=3)
    evidence_text = " ".join(item.text for item in result.evidence).casefold()
    assert not result.coverage.missing_topics
    assert len(result.sources) == 3
    assert all(item.citation.startswith("[src_") for item in result.evidence)
    assert all(term in evidence_text for term in ("sqlite", "streamable", "tor"))


@pytest.mark.integration
async def test_robots_request_is_singleflight_but_rules_remain_path_specific(tmp_path) -> None:
    settings = Settings(privacy_mode="development", database_path=tmp_path / "robots-flight.db")
    database = Database(settings.database_path)
    database.initialize()
    fetcher = RobotsRulesFetcher()
    pipeline = ResearchPipeline(
        settings=settings,
        backend=FakeBackend(),
        fetcher=fetcher,  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )
    private, public = await asyncio.gather(
        pipeline._robots_allowed("https://example.com/private/data"),
        pipeline._robots_allowed("https://example.com/public/data"),
    )
    assert private is False
    assert public is True
    assert fetcher.calls == 1


@pytest.mark.integration
async def test_search_deadline_cancels_orphaned_backend_work(tmp_path) -> None:
    settings = Settings(
        privacy_mode="development",
        database_path=tmp_path / "deadline.db",
        search_min_interval_seconds=0,
    )
    database = Database(settings.database_path)
    database.initialize()
    backend = SlowBackend()
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
        ["slow one", "slow two"],
        language="en",
        recency_days=None,
        limit=3,
        deadline_at=asyncio.get_running_loop().time() + 0.03,
    )
    assert not results
    assert {failure["error"] for failure in failures} == {"ResearchDeadlineExceeded"}
    assert backend.cancelled >= 1
    assert not pipeline._search_inflight


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


@pytest.mark.integration
async def test_search_web_preserves_exact_top_ten_when_all_fetches_fail(tmp_path) -> None:
    question = "exact raw floor question"
    settings = Settings(privacy_mode="development", database_path=tmp_path / "raw-floor.db")
    database = Database(settings.database_path)
    database.initialize()
    backend = OrderedBackend(question)
    pipeline = ResearchPipeline(
        settings=settings,
        backend=backend,
        fetcher=AlwaysFailFetcher(),  # type: ignore[arg-type]
        browser=BrowserFetcher("http://browser", 1, False),
        extractor=PageExtractor(),
        database=database,
        cache=Cache(database),
    )

    result = await pipeline.search_web(question, mode=SearchMode.QUICK, max_sources=3)

    assert backend.limits[0] == (question, 10)
    assert [item.rank for item in result.search_snippets] == list(range(1, 11))
    assert [item.query_role for item in result.search_snippets] == ["exact"] * 10
    assert [item.title for item in result.search_snippets] == [
        f"Exact result {index}" for index in range(1, 11)
    ]
    assert result.search_snippets[3].text == ""
    assert not result.sources
    assert not result.evidence
    assert result.failures
