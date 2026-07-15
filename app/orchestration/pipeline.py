from __future__ import annotations

import asyncio
import logging
import re
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
from app.evidence.prompt_injection import assess_injection
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
    SearchSnippetRecord,
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
        self._search_lock = asyncio.Lock()
        self._last_search_at = 0.0

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
        exact_results_override: list[SearchResult] | None = None,
    ) -> ResearchPackage:
        started = time.monotonic()
        request_id = uuid.uuid4().hex[:16]
        budget = budget_for(mode, self.settings)
        query_limit = (
            min(budget.queries, max(3, max_sources * 2))
            if mode == SearchMode.DEEP
            else budget.queries
        )
        warnings: list[str] = []
        plan = self.planner.plan(query, query_limit)
        if self.enhanced_planner is not None:
            try:
                plan = await self.enhanced_planner.plan(query, plan, query_limit)
            except EnhancedPlannerError as exc:
                warnings.append(
                    f"Local enhanced planner failed ({exc}); deterministic planning was used."
                )
        expansion_round_limit = min(
            budget.rounds,
            rounds_override or budget.rounds,
            max(1, (query_limit + 1) // 2),
        )
        failures: list[dict[str, str]] = []
        if exact_results_override is None:
            exact_raw, exact_errors = await self._search_round(
                [plan.original],
                language=language,
                recency_days=recency_days,
                limit=10,
                allow_fallback=False,
            )
        else:
            exact_raw = [item.model_copy(deep=True) for item in exact_results_override[:10]]
            exact_errors = []
        failures.extend(exact_errors)
        exact_candidates = self._prepare_results(
            exact_raw,
            query,
            include_domains or [],
            exclude_domains or [],
            sort_by_score=False,
        )
        expanded_raw: list[SearchResult] = []
        rounds = 1
        queries_used = 1
        expansion_queries = _unique_queries(
            [
                candidate
                for candidate in plan.queries
                if candidate.casefold() != plan.original.casefold()
            ]
            + [
                candidate
                for round_number in range(1, expansion_round_limit)
                for candidate in self._gap_queries(plan, round_number)
            ]
        )[: max(0, query_limit - 1)]
        queries_per_round = max(
            1,
            (len(expansion_queries) + expansion_round_limit - 1) // expansion_round_limit,
        )
        for round_number in range(expansion_round_limit):
            start = round_number * queries_per_round
            round_queries = expansion_queries[start : start + queries_per_round]
            if not round_queries:
                break
            rounds = round_number + 2  # Exact-query phase plus completed expansion phases.
            queries_used += len(round_queries)
            results, errors = await self._search_round(
                round_queries,
                language=language,
                recency_days=recency_days,
                limit=max(3, budget.raw_results // budget.queries),
            )
            expanded_raw.extend(results)
            failures.extend(errors)
            normalized = self._prepare_results(
                exact_raw + expanded_raw,
                query,
                include_domains or [],
                exclude_domains or [],
            )
            primary_candidate = any(
                source_type(item.url)
                in {"official_documentation", "primary_institution", "source_repository"}
                for item in normalized
            )
            weak_discovery = len(normalized) < budget.pages * 2 or not primary_candidate
            more_rounds = round_number + 1 < expansion_round_limit and queries_used < query_limit
            if mode == SearchMode.DEEP and more_rounds:
                strong_discovery = len(normalized) >= max(6, max_sources * 2) and primary_candidate
                if round_number == 0 or not strong_discovery:
                    continue
            if mode == SearchMode.STANDARD and weak_discovery and more_rounds:
                continue
            if not more_rounds or not weak_discovery:
                break
        candidates = self._prepare_results(
            exact_raw + expanded_raw,
            query,
            include_domains or [],
            exclude_domains or [],
        )
        expanded_candidates = self._prepare_results(
            expanded_raw,
            query,
            include_domains or [],
            exclude_domains or [],
        )
        snippet_limit = min(20, max(10, max_sources))
        exact_snippets = _build_search_snippets(
            exact_candidates,
            limit=min(10, snippet_limit),
            query_role="exact",
        )
        search_snippets = exact_snippets + _build_search_snippets(
            expanded_candidates,
            limit=max(0, snippet_limit - len(exact_snippets)),
            query_role="expanded",
            start_index=len(exact_snippets) + 1,
            exclude_urls={item.url for item in exact_snippets},
        )
        if not candidates:
            warnings.append(
                "No usable search results were returned; no model-memory fallback was used."
            )
        pages_to_fetch = min(budget.pages, max_sources, len(candidates))
        fetch_candidates = _select_fetch_candidates(candidates, pages_to_fetch)
        ranked_sources = await self._retrieve(
            query,
            plan,
            fetch_candidates,
            failures,
            browser_budget=budget.browser_pages,
        )
        sources = [source for source, _ in ranked_sources]
        evidence_limit = min(budget.passages, max(8, max_sources * 3))
        evidence = build_evidence(ranked_sources, evidence_limit, query=query)
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
        if any(item.injection_risk == "high" for item in search_snippets):
            warnings.append("High-risk search snippet text was redacted from answer context.")
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
            search_snippets=search_snippets,
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
            raw_results=len(exact_raw) + len(expanded_raw),
            pages_fetched=pages_to_fetch,
            extraction_failures=sum(item.get("stage") == "fetch_or_extract" for item in failures),
            browser_fallbacks=sum(source.fetch_method == "browser" for source in sources),
        )
        logger.info("research request completed", extra={"request_id": request_id})
        return package

    async def search_exact(
        self,
        query: str,
        *,
        limit: int = 10,
        recency_days: int | None = None,
        language: str = "en",
    ) -> list[SearchResult]:
        """Return safe-normalized exact-query results in SearXNG order."""
        results = await self._search_cached(
            query,
            language=language,
            recency_days=recency_days,
            limit=max(1, limit),
            allow_fallback=False,
        )
        return self._prepare_results(results, query, [], [], sort_by_score=False)

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
            rounds_override=max(1, rounds - 1),
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
        self,
        queries: list[str],
        *,
        language: str,
        recency_days: int | None,
        limit: int,
        allow_fallback: bool = True,
    ) -> tuple[list[SearchResult], list[dict[str, str]]]:
        responses = await asyncio.gather(
            *(
                self._search_cached(
                    query,
                    language=language,
                    recency_days=recency_days,
                    limit=limit,
                    allow_fallback=allow_fallback,
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
        self,
        results: list[SearchResult],
        query: str,
        include: list[str],
        exclude: list[str],
        *,
        sort_by_score: bool = True,
    ) -> list[SearchResult]:
        normalized: list[SearchResult] = []
        for original_rank, result in enumerate(results, start=1):
            try:
                item = normalize_result(result.model_copy(deep=True))
                validate_url(item.url, allow_private=self.settings.allow_private_destinations)
            except (ValueError, UnsafeUrlError):
                continue
            if include and not _domain_matches(item.domain, include):
                continue
            if exclude and _domain_matches(item.domain, exclude):
                continue
            if item.rank is None:
                item.rank = original_rank
            item.preliminary_score = score_search_result(query, item)
            normalized.append(item)
        deduplicated = (
            deduplicate_results(normalized)
            if sort_by_score
            else _deduplicate_exact_results(normalized)
        )
        for item in deduplicated:
            item.preliminary_score = score_search_result(query, item)
        if not sort_by_score:
            return deduplicated
        return sorted(deduplicated, key=lambda item: item.preliminary_score, reverse=True)

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
        self,
        query: str,
        *,
        language: str,
        recency_days: int | None,
        limit: int,
        allow_fallback: bool = True,
    ) -> list[SearchResult]:
        key = Cache.key(
            {
                "query": query,
                "language": language,
                "recency_days": recency_days,
                "limit": limit,
                "allow_fallback": allow_fallback,
                "backend": type(self.backend).__name__,
                "privacy_mode": self.settings.privacy_mode,
            }
        )
        cached = self.cache.get("search", key)
        if isinstance(cached, list):
            return [SearchResult.model_validate(item) for item in cached]
        results = await self._backend_search(
            query, language=language, recency_days=recency_days, limit=limit
        )
        if not results and allow_fallback:
            fallback = _fallback_search_query(query)
            if fallback.casefold() != query.casefold():
                results = await self._backend_search(
                    fallback, language=language, recency_days=recency_days, limit=limit
                )
        if results:
            self._cache_put(
                "search",
                key,
                [result.model_dump(mode="json") for result in results],
                minutes=30,
            )
        return results

    async def _backend_search(
        self, query: str, *, language: str, recency_days: int | None, limit: int
    ) -> list[SearchResult]:
        interval = (
            self.settings.search_min_interval_seconds
            if self.settings.privacy_mode == "strict"
            else 0.0
        )
        async with self._search_lock:
            remaining = interval - (time.monotonic() - self._last_search_at)
            if remaining > 0:
                await asyncio.sleep(remaining)
            try:
                return await self.backend.search(
                    query, language=language, recency_days=recency_days, limit=limit
                )
            finally:
                self._last_search_at = time.monotonic()

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


def _fallback_search_query(query: str) -> str:
    tokens = [
        token
        for token in re.findall(r"[A-Za-z0-9_.+#-]+", query)
        if token.casefold()
        not in {
            "a",
            "an",
            "according",
            "and",
            "are",
            "does",
            "for",
            "from",
            "how",
            "in",
            "is",
            "of",
            "on",
            "the",
            "to",
            "what",
            "when",
            "which",
            "with",
        }
    ]
    return " ".join(tokens[:16]) or query


def _build_search_snippets(
    candidates: list[SearchResult],
    *,
    limit: int,
    query_role: Literal["exact", "expanded"],
    start_index: int = 1,
    exclude_urls: set[str] | None = None,
) -> list[SearchSnippetRecord]:
    if limit <= 0:
        return []
    records: list[SearchSnippetRecord] = []
    excluded = exclude_urls or set()
    for rank, candidate in enumerate(candidates, start=1):
        if len(records) >= min(limit, 20) or candidate.url in excluded:
            continue
        text = " ".join(candidate.snippet.split()).strip()
        if not text and not candidate.title.strip():
            continue
        assessment = assess_injection(f"{candidate.title}\n{text}")
        index = start_index + len(records)
        title = candidate.title
        if assessment.risk == "high":
            title = "[quarantined high-risk search snippet]"
            text = ""
        records.append(
            SearchSnippetRecord(
                snippet_id=f"search_{index:03d}",
                rank=candidate.rank if query_role == "exact" and candidate.rank else rank,
                query_role=query_role,
                url=candidate.url,
                title=title,
                text=text,
                domain=candidate.domain or (urlsplit(candidate.url).hostname or ""),
                engines=candidate.engines or [candidate.engine],
                published_at=candidate.published_at,
                relevance_score=candidate.preliminary_score,
                injection_risk=assessment.risk,  # type: ignore[arg-type]
                injection_reasons=assessment.reasons,
                citation=f"[search_{index:03d}]",
            )
        )
    return records


def _select_fetch_candidates(candidates: list[SearchResult], limit: int) -> list[SearchResult]:
    if limit <= 0:
        return []
    selected: list[SearchResult] = [candidates[0]] if candidates else []
    if len(selected) >= limit:
        return selected
    top_score = candidates[0].preliminary_score if candidates else 0.0
    eligible = [
        candidate
        for candidate in candidates[: max(10, limit * 3)]
        if candidate.preliminary_score >= max(0.15, top_score * 0.55)
    ]
    primary = next(
        (
            candidate
            for candidate in eligible
            if source_type(candidate.url)
            in {"official_documentation", "primary_institution", "source_repository"}
            and candidate.canonical_url not in {item.canonical_url for item in selected}
        ),
        None,
    )
    if primary is not None:
        selected.append(primary)
    for candidate in eligible:
        if len(selected) >= limit:
            break
        if candidate.canonical_url not in {
            item.canonical_url for item in selected
        } and candidate.domain not in {item.domain for item in selected}:
            selected.append(candidate)
    for candidate in candidates:
        if len(selected) >= limit:
            break
        if candidate.canonical_url not in {item.canonical_url for item in selected}:
            selected.append(candidate)
    return selected


def _unique_queries(queries: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for query in queries:
        compact = " ".join(query.split()).strip()
        key = compact.casefold()
        if compact and key not in seen:
            seen.add(key)
            unique.append(compact)
    return unique


def _deduplicate_exact_results(results: list[SearchResult]) -> list[SearchResult]:
    """Preserve SearXNG rank while removing only exact canonical-URL duplicates."""
    unique: list[SearchResult] = []
    by_url: dict[str, SearchResult] = {}
    for result in results:
        key = result.canonical_url or result.url
        existing = by_url.get(key)
        if existing is not None:
            existing.engines = sorted(set(existing.engines + result.engines))
            existing.search_score = max(existing.search_score, result.search_score)
            if len(result.snippet) > len(existing.snippet):
                existing.snippet = result.snippet
            continue
        by_url[key] = result
        unique.append(result)
    return unique
