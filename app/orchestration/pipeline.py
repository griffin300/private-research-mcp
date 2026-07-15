from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit

from app.config import Settings
from app.evidence.contradictions import detect_contradictions
from app.evidence.coverage import analyze_coverage
from app.evidence.ledger import build_evidence
from app.extract.chunker import chunk_text
from app.extract.extractor import ExtractionError, PageExtractor
from app.fetch.browser_fetcher import BrowserFetcher
from app.fetch.http_fetcher import FetchError, HttpFetcher
from app.fetch.robots import robots_allows
from app.fetch.url_safety import UnsafeUrlError, validate_url
from app.models import (
    ExtractedPage,
    FetchResult,
    HealthReport,
    Passage,
    PrivacySummary,
    ResearchPackage,
    SearchMode,
    SearchResult,
    SourceRecord,
)
from app.orchestration.budgets import budget_for
from app.orchestration.planner import EnhancedPlannerError, EnhancedQueryPlanner
from app.privacy.network_checks import configuration_network_check
from app.privacy.redaction import query_fingerprint
from app.ranking.freshness import freshness_score
from app.ranking.reranker import HybridReranker
from app.ranking.source_quality import explain_source_quality, score_search_result, source_type
from app.search.base import SearchBackend
from app.search.deduplication import deduplicate_results
from app.search.normalization import normalize_result
from app.search.query_expansion import HeuristicQueryPlanner, QueryPlan
from app.storage.cache import Cache
from app.storage.database import Database

logger = logging.getLogger(__name__)


class ResearchPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        backend: SearchBackend,
        fetcher: HttpFetcher,
        browser: BrowserFetcher,
        extractor: PageExtractor,
        database: Database,
        cache: Cache,
    ) -> None:
        self.settings = settings
        self.backend = backend
        self.fetcher = fetcher
        self.browser = browser
        self.extractor = extractor
        self.database = database
        self.cache = cache
        self.planner = HeuristicQueryPlanner()
        self.enhanced_planner = (
            EnhancedQueryPlanner(
                settings.lm_studio_planner_base_url,
                settings.lm_studio_planner_model,
                settings.request_timeout_seconds,
            )
            if settings.allow_internal_llm_planner
            else None
        )
        self.reranker = HybridReranker()

    async def search_web(
        self,
        query: str,
        *,
        mode: SearchMode = SearchMode.STANDARD,
        max_sources: int = 8,
        recency_days: int | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        language: str = "en",
        rounds_override: int | None = None,
    ) -> ResearchPackage:
        started = time.monotonic()
        request_id = uuid.uuid4().hex[:16]
        budget = budget_for(mode, self.settings)
        warnings: list[str] = []
        plan = self.planner.plan(query, budget.queries)
        if self.enhanced_planner is not None:
            try:
                plan = await self.enhanced_planner.plan(query, plan, budget.queries)
            except EnhancedPlannerError as exc:
                warnings.append(
                    f"Local enhanced planner failed ({exc}); deterministic planning was used."
                )
        rounds_limit = min(budget.rounds, rounds_override or budget.rounds)
        raw: list[SearchResult] = []
        failures: list[dict[str, str]] = []
        rounds = 0
        queries_used = 0
        queries_per_round = max(2, (budget.queries + rounds_limit - 1) // rounds_limit)
        for round_number in range(rounds_limit):
            remaining_queries = budget.queries - queries_used
            if remaining_queries <= 0:
                break
            candidates_for_round = (
                plan.queries if round_number == 0 else self._gap_queries(plan, round_number)
            )
            round_queries = candidates_for_round[: min(queries_per_round, remaining_queries)]
            if not round_queries:
                break
            rounds += 1
            queries_used += len(round_queries)
            results, errors = await self._search_round(
                round_queries,
                language=language,
                recency_days=recency_days,
                limit=max(3, budget.raw_results // budget.queries),
            )
            raw.extend(results)
            failures.extend(errors)
            normalized = self._prepare_results(
                raw, query, include_domains or [], exclude_domains or []
            )
            primary_candidate = any(
                source_type(item.url)
                in {"official_documentation", "primary_institution", "source_repository"}
                for item in normalized
            )
            weak_discovery = len(normalized) < budget.pages * 2 or not primary_candidate
            more_rounds = round_number + 1 < rounds_limit and queries_used < budget.queries
            if mode == SearchMode.DEEP and more_rounds:
                continue
            if mode == SearchMode.STANDARD and weak_discovery and more_rounds:
                continue
            if not more_rounds or not weak_discovery:
                break
        candidates = self._prepare_results(raw, query, include_domains or [], exclude_domains or [])
        if not candidates:
            warnings.append(
                "No usable search results were returned; no model-memory fallback was used."
            )
        pages_to_fetch = min(budget.pages, max_sources, len(candidates))
        ranked_sources = await self._retrieve(
            query,
            plan,
            candidates[:pages_to_fetch],
            failures,
            browser_budget=budget.browser_pages,
        )
        sources = [source for source, _ in ranked_sources]
        evidence = build_evidence(ranked_sources, budget.passages)
        coverage = analyze_coverage(plan.topics or [query], evidence, sources)
        contradictions = detect_contradictions(evidence) if mode == SearchMode.DEEP else []
        if not self.settings.enable_embeddings:
            warnings.append(
                "Local embedding model unavailable or disabled; lexical ranking was used."
            )
        if any(
            item.injection_risk == "high" for _, passages in ranked_sources for item in passages
        ):
            warnings.append("High-risk prompt-injection content was quarantined from evidence.")
        if plan.time_sensitive and any(source.published_at is None for source in sources):
            warnings.append(
                "One or more retained sources are undated for a time-sensitive question."
            )
        unresolved = list(coverage.missing_topics)
        if not coverage.primary_source_present:
            unresolved.append("No clearly identifiable primary source was retained.")
        package = ResearchPackage(
            query=query,
            mode=mode.value,
            request_id=request_id,
            search_rounds=rounds,
            coverage=coverage,
            sources=sources,
            evidence=evidence,
            contradictions=contradictions,
            unresolved_questions=list(dict.fromkeys(unresolved)),
            warnings=warnings,
            failures=failures,
            privacy=PrivacySummary(
                search_transport="tor-search"
                if self.settings.privacy_mode == "strict"
                else "development",
                fetch_transport="tor-fetch"
                if self.settings.privacy_mode == "strict"
                else "development",
                direct_egress_allowed=self.settings.direct_egress_allowed,
                mode=self.settings.privacy_mode,
            ),
        )
        self._record_request(
            package,
            int((time.monotonic() - started) * 1000),
            queries_generated=queries_used,
            raw_results=len(raw),
            pages_fetched=pages_to_fetch,
            extraction_failures=sum(item.get("stage") == "fetch_or_extract" for item in failures),
            browser_fallbacks=sum(source.fetch_method == "browser" for source in sources),
        )
        logger.info("research request completed", extra={"request_id": request_id})
        return package

    async def deep_research(
        self,
        question: str,
        *,
        max_search_rounds: int = 4,
        max_sources: int = 20,
        recency_days: int | None = None,
        research_depth: str = "normal",
    ) -> ResearchPackage:
        requested = max(2, max_search_rounds)
        rounds = requested if research_depth == "extensive" else min(requested, 3)
        return await self.search_web(
            question,
            mode=SearchMode.DEEP,
            max_sources=max_sources,
            recency_days=recency_days,
            rounds_override=rounds,
        )

    async def read_url(self, url: str, question: str | None = None) -> dict[str, object]:
        validate_url(url, allow_private=self.settings.allow_private_destinations)
        if not await self._robots_allowed(url):
            raise FetchError("robots.txt disallows retrieval")
        fetched = await self._fetch_cached(url)
        page = self._extract_cached(fetched)
        passages = self.reranker.rank(question or page.title, chunk_text(page.text))
        safe: list[Passage] = []
        from app.evidence.prompt_injection import assess_injection

        for passage in passages:
            assessment = assess_injection(passage.text)
            passage.injection_risk = assessment.risk  # type: ignore[assignment]
            passage.injection_reasons = assessment.reasons
            if assessment.risk != "high":
                safe.append(passage)
        return {
            "url": page.url,
            "title": page.title,
            "metadata": page.model_dump(exclude={"text"}, mode="json"),
            "passages": [passage.model_dump(mode="json") for passage in safe[:20]],
            "quarantined_passages": len(passages) - len(safe),
            "privacy": {
                "fetch_transport": "tor-fetch"
                if self.settings.privacy_mode == "strict"
                else "development",
                "direct_egress_allowed": self.settings.direct_egress_allowed,
            },
        }

    async def status(self) -> HealthReport:
        searxng, database, browser = await asyncio.gather(
            self.backend.health(),
            asyncio.to_thread(self._database_health),
            self.browser.health(),
        )
        network = configuration_network_check(self.settings)
        components: dict[str, dict[str, Any]] = {
            "service": {"status": "healthy"},
            "searxng": searxng,
            "search_proxy": {
                "status": "configured" if self.settings.search_proxy_url else "unhealthy"
            },
            "fetch_proxy": {
                "status": "configured" if self.settings.fetch_proxy_url else "unhealthy"
            },
            "browser": browser,
            "database": database,
            "ranking_models": {
                "embeddings": "enabled" if self.settings.enable_embeddings else "lexical-only",
                "reranker": "enabled" if self.settings.enable_reranker else "disabled",
            },
            "cache": self.database.stats(),
            "network_policy": network,
        }
        unhealthy = any(value.get("status") == "unhealthy" for value in components.values())
        status: Literal["healthy", "degraded", "unhealthy"]
        if unhealthy and self.settings.privacy_mode == "strict":
            status = "unhealthy"
        elif unhealthy:
            status = "degraded"
        else:
            status = "healthy"
        return HealthReport(
            status=status,
            components=components,
            privacy_mode=self.settings.privacy_mode,
            unsafe_fallback_enabled=self.settings.direct_egress_allowed,
        )

    async def _search_round(
        self, queries: list[str], *, language: str, recency_days: int | None, limit: int
    ) -> tuple[list[SearchResult], list[dict[str, str]]]:
        responses = await asyncio.gather(
            *(
                self._search_cached(
                    query, language=language, recency_days=recency_days, limit=limit
                )
                for query in queries
            ),
            return_exceptions=True,
        )
        results: list[SearchResult] = []
        failures: list[dict[str, str]] = []
        for query, response in zip(queries, responses, strict=True):
            if isinstance(response, BaseException):
                failures.append(
                    {
                        "stage": "search",
                        "query_hash": query_fingerprint(query),
                        "error": type(response).__name__,
                    }
                )
            else:
                results.extend(response)
        return results, failures

    def _prepare_results(
        self, results: list[SearchResult], query: str, include: list[str], exclude: list[str]
    ) -> list[SearchResult]:
        normalized: list[SearchResult] = []
        for result in results:
            try:
                item = normalize_result(result)
                validate_url(item.url, allow_private=self.settings.allow_private_destinations)
            except (ValueError, UnsafeUrlError):
                continue
            if include and not _domain_matches(item.domain, include):
                continue
            if exclude and _domain_matches(item.domain, exclude):
                continue
            item.preliminary_score = score_search_result(query, item)
            normalized.append(item)
        return sorted(
            deduplicate_results(normalized), key=lambda item: item.preliminary_score, reverse=True
        )

    async def _retrieve(
        self,
        query: str,
        plan: QueryPlan,
        candidates: list[SearchResult],
        failures: list[dict[str, str]],
        *,
        browser_budget: int,
    ) -> list[tuple[SourceRecord, list[Passage]]]:
        tasks = [
            self._retrieve_one(
                query,
                plan,
                candidate,
                index,
                allow_browser_fallback=index <= browser_budget,
            )
            for index, candidate in enumerate(candidates, 1)
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        retained: list[tuple[SourceRecord, list[Passage]]] = []
        seen_hashes: set[str] = set()
        for candidate, response in zip(candidates, responses, strict=True):
            if isinstance(response, BaseException):
                failures.append(
                    {
                        "stage": "fetch_or_extract",
                        "url": candidate.url,
                        "error": type(response).__name__,
                    }
                )
                continue
            source, passages = response
            if source.content_hash in seen_hashes:
                failures.append(
                    {"stage": "deduplication", "url": candidate.url, "error": "duplicate_content"}
                )
                continue
            seen_hashes.add(source.content_hash)
            retained.append((source, passages))
        return retained

    async def _retrieve_one(
        self,
        query: str,
        plan: QueryPlan,
        result: SearchResult,
        index: int,
        *,
        allow_browser_fallback: bool,
    ) -> tuple[SourceRecord, list[Passage]]:
        if not await self._robots_allowed(result.url):
            raise FetchError("robots.txt disallows retrieval")
        try:
            fetched = await self._fetch_cached(result.url)
            page = self._extract_cached(fetched)
        except (FetchError, ExtractionError):
            if not self.settings.enable_browser or not allow_browser_fallback:
                raise
            fetched = await self.browser.fetch(result.url)
            self._cache_put("pages", self._page_key(result.url), fetched.model_dump(mode="json"))
            page = self._extract_cached(fetched)
        passages = self.reranker.rank(query, chunk_text(page.text))[:8]
        quality = 0.65 * result.preliminary_score + 0.35 * freshness_score(
            page.updated_at or page.published_at, time_sensitive=plan.time_sensitive
        )
        source = SourceRecord(
            source_id=f"src_{index:03d}",
            url=page.url,
            title=page.title,
            domain=urlsplit(page.url).hostname or result.domain,
            published_at=page.published_at,
            updated_at=page.updated_at,
            retrieved_at=page.retrieved_at,
            source_type=source_type(page.url),
            quality_score=round(quality, 4),
            quality_explanation=explain_source_quality(
                result, dated=bool(page.updated_at or page.published_at)
            ),
            relevance_score=passages[0].relevance_score if passages else 0.0,
            fetch_method=fetched.method,
            content_hash=page.content_hash,
        )
        return source, passages

    def _record_request(
        self,
        package: ResearchPackage,
        duration_ms: int,
        *,
        queries_generated: int,
        raw_results: int,
        pages_fetched: int,
        extraction_failures: int,
        browser_fallbacks: int,
    ) -> None:
        raw_query = package.query if self.settings.store_search_history else None
        self.database.execute(
            "INSERT OR REPLACE INTO requests "
            "(request_id, query_hash, raw_query, created_at, duration_ms, source_count, "
            "evidence_count, coverage_score, queries_generated, raw_results, pages_fetched, "
            "extraction_failures, browser_fallbacks) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                package.request_id,
                query_fingerprint(package.query),
                raw_query,
                datetime.now(UTC).isoformat(),
                duration_ms,
                len(package.sources),
                len(package.evidence),
                package.coverage.score,
                queries_generated,
                raw_results,
                pages_fetched,
                extraction_failures,
                browser_fallbacks,
            ),
        )
        expires_at = (
            datetime.now(UTC) + timedelta(days=self.settings.cache_retention_days)
        ).isoformat()
        evidence_rows: list[tuple[Any, ...]] = []
        index_rows: list[tuple[Any, ...]] = []
        for evidence in package.evidence:
            record_id = f"{package.request_id}:{evidence.evidence_id}"
            evidence_rows.append((record_id, expires_at))
            index_rows.append(
                (record_id, evidence.source_id, evidence.heading or "", evidence.text)
            )
        self.database.execute_many(
            "INSERT OR REPLACE INTO evidence_records VALUES (?, ?)", evidence_rows
        )
        self.database.execute_many(
            "INSERT INTO evidence_fts(evidence_id, source_id, heading, text) VALUES (?, ?, ?, ?)",
            index_rows,
        )
        self._cache_put(
            "evidence",
            package.request_id,
            [item.model_dump(mode="json") for item in package.evidence],
        )

    async def _search_cached(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        key = Cache.key(
            {
                "query": query,
                "language": language,
                "recency_days": recency_days,
                "limit": limit,
                "backend": type(self.backend).__name__,
                "privacy_mode": self.settings.privacy_mode,
            }
        )
        cached = self.cache.get("search", key)
        if isinstance(cached, list):
            return [SearchResult.model_validate(item) for item in cached]
        results = await self.backend.search(
            query, language=language, recency_days=recency_days, limit=limit
        )
        self._cache_put(
            "search",
            key,
            [result.model_dump(mode="json") for result in results],
            minutes=30,
        )
        return results

    async def _fetch_cached(self, url: str) -> FetchResult:
        key = self._page_key(url)
        if self.cache.get("failures", key) is not None:
            raise FetchError("recent cached retrieval failure")
        cached = self.cache.get("pages", key)
        if isinstance(cached, dict):
            result = FetchResult.model_validate(cached)
            result.method = "cache"
            return result
        try:
            result = await self.fetcher.fetch(url)
        except FetchError as exc:
            self._cache_put("failures", key, {"error": type(exc).__name__}, minutes=5)
            raise
        self._cache_put("pages", key, result.model_dump(mode="json"))
        return result

    def _extract_cached(self, fetched: FetchResult) -> ExtractedPage:
        key = self._page_key(fetched.final_url)
        cached = self.cache.get("extracted", key)
        if isinstance(cached, dict):
            return ExtractedPage.model_validate(cached)
        page = self.extractor.extract(fetched)
        self._cache_put("extracted", key, page.model_dump(mode="json"))
        return page

    def _cache_put(
        self, namespace: str, key: str, value: Any, *, minutes: int | None = None
    ) -> None:
        if self.settings.cache_retention_days <= 0:
            return
        ttl = (
            timedelta(minutes=minutes)
            if minutes is not None
            else timedelta(days=self.settings.cache_retention_days)
        )
        self.cache.put(namespace, key, value, ttl)

    def _page_key(self, url: str) -> str:
        return Cache.key(
            {
                "url": url,
                "max_bytes": self.settings.max_response_bytes,
                "browser": self.settings.enable_browser,
                "privacy_mode": self.settings.privacy_mode,
            }
        )

    async def _robots_allowed(self, url: str) -> bool:
        parsed = urlsplit(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        user_agent = "PrivateResearchMCP"
        key = Cache.key({"url": robots_url, "user_agent": user_agent})
        cached = self.cache.get("robots", key)
        if isinstance(cached, bool):
            return cached
        try:
            result = await self.fetcher.fetch(robots_url)
        except FetchError:
            return True
        allowed = robots_allows(result.body, url, user_agent)
        self._cache_put("robots", key, allowed, minutes=360)
        return allowed

    def _database_health(self) -> dict[str, object]:
        try:
            return {
                "status": "healthy" if self.database.integrity() else "unhealthy",
                **self.database.stats(),
            }
        except Exception as exc:  # Boundary: database driver exceptions vary.
            return {"status": "unhealthy", "error": type(exc).__name__}

    @staticmethod
    def _gap_queries(plan: QueryPlan, round_number: int) -> list[str]:
        suffixes = (
            "primary source specification",
            "research paper benchmark",
            "issue tracker discussion",
            "release notes current",
        )
        suffix = suffixes[min(round_number - 1, len(suffixes) - 1)]
        return [f"{topic} {suffix}" for topic in plan.topics[:5]] or [f"{plan.original} {suffix}"]


def _domain_matches(domain: str, patterns: Iterable[str]) -> bool:
    normalized = domain.lower().rstrip(".")
    return any(
        normalized == pattern.lower().lstrip(".")
        or normalized.endswith(f".{pattern.lower().lstrip('.')}")
        for pattern in patterns
    )
