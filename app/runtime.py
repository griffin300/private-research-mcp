from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.extract.extractor import PageExtractor
from app.fetch.browser_fetcher import BrowserFetcher
from app.fetch.http_fetcher import HttpFetcher
from app.fetch.policies import FetchPolicy
from app.orchestration.pipeline import ResearchPipeline
from app.search.searxng import SearxngBackend
from app.storage.cache import Cache
from app.storage.database import Database
from app.storage.migrations import migrate
from app.storage.retention import clean_expired


@dataclass(slots=True)
class Runtime:
    settings: Settings
    database: Database
    pipeline: ResearchPipeline


def create_runtime(settings: Settings | None = None) -> Runtime:
    settings = settings or Settings()
    database = Database(settings.database_path)
    migrate(database)
    database.set_query_data_persistence(settings.cache_retention_days > 0)
    clean_expired(database, settings.cache_retention_days)
    fetcher = HttpFetcher(
        policy=FetchPolicy(
            max_response_bytes=settings.max_response_bytes,
            max_redirects=settings.max_redirects,
            timeout_seconds=settings.request_timeout_seconds,
        ),
        proxy_url=settings.fetch_proxy_url or None,
        strict_privacy=settings.privacy_mode == "strict",
        allow_private=settings.allow_private_destinations,
        per_domain_concurrency=settings.per_domain_concurrency,
    )
    backend = SearxngBackend(
        settings.searxng_base_url,
        settings.request_timeout_seconds,
        settings.searxng_recovery_delay_seconds,
    )
    browser = BrowserFetcher(
        settings.browser_service_url, settings.request_timeout_seconds, settings.enable_browser
    )
    cache = Cache(database)
    pipeline = ResearchPipeline(
        settings=settings,
        backend=backend,
        fetcher=fetcher,
        browser=browser,
        extractor=PageExtractor(),
        database=database,
        cache=cache,
    )
    return Runtime(settings, database, pipeline)
