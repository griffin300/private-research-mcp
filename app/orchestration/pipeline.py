from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypeVar, cast
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
from app.privacy.redaction import has_sensitive_query, query_fingerprint, redact_url
from app.ranking.freshness import freshness_score
from app.ranking.lexical import meaningful_tokens
from app.ranking.reranker import HybridReranker
from app.ranking.source_quality import explain_source_quality, score_search_result, source_type
from app.search.base import SearchBackend
from app.search.deduplication import deduplicate_results
from app.search.normalization import normalize_result
from app.search.official_sources import (
    distinctive_anchor_coverage,
    distinctive_query_tokens,
    domain_matches_authority,
    official_source_candidates,
)
from app.search.query_expansion import HeuristicQueryPlanner, QueryPlan, split_compound_query
from app.storage.cache import Cache
from app.storage.database import Database

logger = logging.getLogger(__name__)
_T = TypeVar("_T")


@dataclass(slots=True)
class _Flight:
    task: asyncio.Task[Any]
    waiters: int = 0


@dataclass(slots=True)
class _BrowserFallbackBudget:
    remaining: int

    def claim(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


@dataclass(slots=True)
class _SearchFallbackBudget:
    remaining: int
    used: int = 0

    def claim(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        self.used += 1
        return True


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
        self._search_inflight: dict[str, _Flight] = {}
        self._fetch_inflight: dict[str, _Flight] = {}
        self._robots_inflight: dict[str, _Flight] = {}

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
        deadline_seconds_override: float | None = None,
    ) -> ResearchPackage:
        started = time.monotonic()
        request_id = uuid.uuid4().hex[:16]
        budget = budget_for(mode, self.settings)
        configured_deadline = getattr(self.settings, f"{mode.value}_deadline_seconds")
        deadline_seconds = (
            configured_deadline
            if deadline_seconds_override is None
            else min(configured_deadline, max(0.01, deadline_seconds_override))
        )
        deadline_at = started + deadline_seconds
        search_deadline_at = started + deadline_seconds * 0.55
        query_limit = (
            min(budget.queries, max(3, max_sources * 2))
            if mode == SearchMode.DEEP
            else budget.queries
        )
        warnings: list[str] = []
        detection_limit = 256
        detected_queries = split_compound_query(query, limit=detection_limit)
        facet_limit = min(6, query_limit)
        focused_queries = detected_queries[:facet_limit]
        omitted_facet_count = max(0, len(detected_queries) - len(focused_queries))
        is_compound = len(detected_queries) > 1
        if is_compound:
            query_limit = min(query_limit, max(len(focused_queries), len(focused_queries) * 2))
            plan = _plan_compound_query(self.planner, query, focused_queries, query_limit)
            warnings.append(
                f"Decomposed an explicit query batch into {len(focused_queries)} focused facets."
            )
            if omitted_facet_count:
                omitted_label = (
                    f"at least {omitted_facet_count}"
                    if len(detected_queries) == detection_limit
                    else str(omitted_facet_count)
                )
                warnings.append(
                    f"The batch exceeded the bounded {facet_limit}-facet limit; "
                    f"{omitted_label} additional question(s) were left unresolved."
                )
        else:
            plan = self.planner.plan(query, query_limit)
        if self.enhanced_planner is not None and not is_compound:
            try:
                plan = await self.enhanced_planner.plan(query, plan, query_limit)
            except EnhancedPlannerError as exc:
                warnings.append(
                    f"Local enhanced planner failed ({exc}); deterministic planning was used."
                )
        ranking_queries = focused_queries if is_compound else _ranking_queries(plan, query)
        expansion_round_limit = (
            1
            if is_compound
            else min(
                budget.rounds,
                rounds_override or budget.rounds,
                max(1, (query_limit + 1) // 2),
            )
        )
        failures: list[dict[str, str]] = []
        exact_queries = focused_queries if is_compound else [plan.original]
        exact_groups: list[list[SearchResult]] = []
        if exact_results_override is None:
            exact_limit = (
                10
                if not is_compound
                else max(
                    3,
                    min(10, min(20, budget.raw_results) // len(exact_queries)),
                )
            )
            exact_raw, exact_errors = await self._search_round(
                exact_queries,
                language=language,
                recency_days=recency_days,
                limit=exact_limit,
                allow_fallback=False,
                interleave=is_compound,
                deadline_at=search_deadline_at,
                groups_out=exact_groups,
            )
        else:
            exact_raw = [item.model_copy(deep=True) for item in exact_results_override[:10]]
            exact_errors = []
            if len(exact_queries) == 1:
                exact_groups.append(exact_raw)
        failures.extend(exact_errors)
        exact_candidates = self._prepare_results(
            exact_raw,
            query,
            include_domains or [],
            exclude_domains or [],
            sort_by_score=False,
            relevance_queries=ranking_queries,
        )
        official_raw = official_source_candidates(query)
        if official_raw:
            warnings.append(
                "Added bounded canonical-source candidates derived locally from public identifiers."
            )
        expanded_raw: list[SearchResult] = []
        rounds = 1
        queries_used = len(exact_queries)
        exact_query_keys = {candidate.casefold() for candidate in exact_queries}
        reserved_fallbacks = 1 if query_limit > len(exact_queries) + 1 else 0
        expansion_queries = _unique_queries(
            [
                candidate
                for candidate in plan.queries
                if candidate.casefold() not in exact_query_keys
            ]
            + [
                candidate
                for round_number in range(1, expansion_round_limit)
                for candidate in self._gap_queries(plan, round_number)
            ]
        )[: max(0, query_limit - len(exact_queries) - reserved_fallbacks)]
        queries_per_round = (
            len(expansion_queries) if is_compound else min(2, len(expansion_queries))
        )
        planned_expansion_calls = (
            len(expansion_queries)
            if is_compound
            else min(expansion_round_limit * queries_per_round, len(expansion_queries))
        )
        expansion_result_limit = max(
            3,
            min(
                15,
                max(0, budget.raw_results - len(exact_raw)) // max(1, planned_expansion_calls),
            ),
        )
        search_fallback_budget = _SearchFallbackBudget(reserved_fallbacks)
        weak_rounds = 0
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
                limit=expansion_result_limit,
                deadline_at=search_deadline_at,
                fallback_budget=search_fallback_budget,
            )
            expanded_raw.extend(results)
            failures.extend(errors)
            normalized = self._prepare_results(
                exact_raw + expanded_raw,
                query,
                include_domains or [],
                exclude_domains or [],
                relevance_queries=ranking_queries,
            )
            relevant_results = [
                item for item in normalized if score_search_result(query, item) >= 0.30
            ]
            primary_candidate = any(
                _is_query_aligned_primary(query, item) for item in relevant_results
            )
            minimum_relevant = max(2, min(4, max_sources // 2))
            weak_discovery = len(relevant_results) < minimum_relevant or not primary_candidate
            useful_round = any(score_search_result(query, item) >= 0.30 for item in results)
            weak_rounds = 0 if useful_round else weak_rounds + 1
            more_rounds = (
                round_number + 1 < expansion_round_limit
                and queries_used + search_fallback_budget.used < query_limit
            )
            if weak_rounds >= 2:
                break
            if mode == SearchMode.DEEP and more_rounds:
                strong_discovery = (
                    len(relevant_results) >= max(6, max_sources) and primary_candidate
                )
                if round_number == 0 or not strong_discovery:
                    continue
            if mode == SearchMode.STANDARD and weak_discovery and more_rounds:
                continue
            if not more_rounds or not weak_discovery:
                break
        candidates = self._prepare_results(
            exact_raw + expanded_raw + official_raw,
            query,
            include_domains or [],
            exclude_domains or [],
            relevance_queries=ranking_queries,
        )
        expanded_candidates = self._prepare_results(
            expanded_raw,
            query,
            include_domains or [],
            exclude_domains or [],
            relevance_queries=ranking_queries,
        )
        snippet_limit = min(20, max(10, max_sources))
        exact_snippets = _build_search_snippets(
            exact_candidates,
            limit=min(10, snippet_limit),
            query_role="exact",
        )
        search_snippets = exact_snippets + _build_search_snippets(
            expanded_candidates,
            limit=(
                min(10, max_sources) if is_compound else max(0, snippet_limit - len(exact_snippets))
            ),
            query_role="expanded",
            start_index=len(exact_snippets) + 1,
            exclude_urls={item.url for item in exact_snippets},
        )
        if not candidates:
            warnings.append(
                "No usable search results were returned; no model-memory fallback was used."
            )
        pages_to_fetch = min(budget.pages, max_sources, len(candidates))
        raw_preferred_by_query: dict[str, SearchResult] = {}
        if is_compound and exact_groups:
            for facet, group in zip(focused_queries, exact_groups, strict=False):
                prepared_group = self._prepare_results(
                    group,
                    facet,
                    include_domains or [],
                    exclude_domains or [],
                    sort_by_score=False,
                    relevance_queries=[facet],
                )
                if prepared_group:
                    raw_preferred_by_query[facet] = prepared_group[0]
        elif is_compound:
            raw_preferred_by_query = _preferred_exact_candidates(exact_candidates, focused_queries)
        candidates = self._prioritize_fetchable_candidates(
            candidates,
            minimum=pages_to_fetch,
            preserve_failed={
                _candidate_key(candidate)
                for candidate in raw_preferred_by_query.values()
                if self.settings.enable_browser and budget.browser_pages > 0
            },
        )
        candidate_keys = {_candidate_key(candidate) for candidate in candidates}
        preferred_by_query = {
            facet: candidate
            for facet, candidate in raw_preferred_by_query.items()
            if _candidate_key(candidate) in candidate_keys
        }
        candidate_pool_limit = (
            min(
                len(candidates),
                max(pages_to_fetch * 3, pages_to_fetch + 2 * len(ranking_queries)),
            )
            if len(ranking_queries) > 1
            else pages_to_fetch
        )
        fetch_candidates = _select_fetch_candidates(
            candidates,
            candidate_pool_limit,
            relevance_queries=ranking_queries if len(ranking_queries) > 1 else None,
            preferred_candidates=list(preferred_by_query.values()),
        )
        ranked_sources, pages_attempted = await self._retrieve(
            query,
            plan,
            fetch_candidates,
            failures,
            browser_budget=budget.browser_pages,
            relevance_queries=ranking_queries,
            deadline_at=deadline_at,
            attempt_limit=pages_to_fetch,
            preferred_by_query=preferred_by_query,
        )
        sources = [source for source, _ in ranked_sources]
        # Keep the verified context compact for local models: one passage per
        # requested source on average, with an eight-record floor for compound
        # facet coverage. Deep mode can still scale with max_sources.
        evidence_limit = min(budget.passages, max(8, max_sources))
        evidence = build_evidence(
            ranked_sources,
            evidence_limit,
            query=query,
            queries=ranking_queries if len(ranking_queries) > 1 else None,
        )
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
        if any(item.get("error") == "ResearchDeadlineExceeded" for item in failures):
            warnings.append(
                "The bounded research deadline was reached; completed exact results and "
                "evidence were returned instead of allowing the MCP request to time out."
            )
        if plan.time_sensitive and any(source.published_at is None for source in sources):
            warnings.append(
                "One or more retained sources are undated for a time-sensitive question."
            )
        unresolved = list(coverage.missing_topics)
        if omitted_facet_count:
            unresolved.append(
                "Additional batched questions were not processed because the bounded facet "
                "limit was reached."
            )
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
            queries_generated=queries_used + search_fallback_budget.used,
            raw_results=len(exact_raw) + len(expanded_raw),
            pages_fetched=pages_attempted,
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
        deadline_seconds_override: float | None = None,
    ) -> ResearchPackage:
        requested = max(2, max_search_rounds)
        rounds = requested if research_depth == "extensive" else min(requested, 3)
        return await self.search_web(
            question,
            mode=SearchMode.DEEP,
            max_sources=max_sources,
            recency_days=recency_days,
            rounds_override=max(1, rounds - 1),
            deadline_seconds_override=deadline_seconds_override,
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
        metadata = page.model_dump(exclude={"text"}, mode="json")
        metadata["url"] = redact_url(str(metadata["url"]))
        metadata["title"] = _redact_possible_url(str(metadata["title"]))
        if metadata.get("canonical_url"):
            metadata["canonical_url"] = redact_url(str(metadata["canonical_url"]))
        return {
            "url": redact_url(page.url),
            "title": _redact_possible_url(page.title),
            "metadata": metadata,
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
        fallback_budget: _SearchFallbackBudget | None = None,
        interleave: bool = False,
        deadline_at: float | None = None,
        groups_out: list[list[SearchResult]] | None = None,
    ) -> tuple[list[SearchResult], list[dict[str, str]]]:
        tasks = [
            asyncio.create_task(
                self._search_cached(
                    query,
                    language=language,
                    recency_days=recency_days,
                    limit=limit,
                    allow_fallback=allow_fallback and fallback_budget is None,
                )
            )
            for query in queries
        ]
        await _wait_until_deadline(tasks, deadline_at)
        groups: list[list[SearchResult]] = []
        failures: list[dict[str, str]] = []
        for query, task in zip(queries, tasks, strict=True):
            if task.cancelled():
                failures.append(
                    {
                        "stage": "search",
                        "query_hash": query_fingerprint(query),
                        "error": "ResearchDeadlineExceeded",
                    }
                )
                groups.append([])
                continue
            try:
                groups.append(task.result())
            except BaseException as exc:
                failures.append(
                    {
                        "stage": "search",
                        "query_hash": query_fingerprint(query),
                        "error": type(exc).__name__,
                    }
                )
                groups.append([])
        if allow_fallback and fallback_budget is not None:
            for empty_index, group in enumerate(groups):
                if group:
                    continue
                fallback_query = _fallback_search_query(queries[empty_index])
                if fallback_query.casefold() == queries[empty_index].casefold():
                    continue
                if not fallback_budget.claim():
                    break
                try:
                    remaining = (
                        None if deadline_at is None else max(0.0, deadline_at - time.monotonic())
                    )
                    operation = self._search_cached(
                        fallback_query,
                        language=language,
                        recency_days=recency_days,
                        limit=limit,
                        allow_fallback=False,
                    )
                    groups[empty_index] = (
                        await operation
                        if remaining is None
                        else await asyncio.wait_for(operation, timeout=remaining)
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    failures.append(
                        {
                            "stage": "search",
                            "query_hash": query_fingerprint(fallback_query),
                            "error": type(exc).__name__,
                        }
                    )
                break
        if groups_out is not None:
            groups_out.extend(groups)
        results = (
            _interleave_results(groups)
            if interleave
            else [item for group in groups for item in group]
        )
        return results, failures

    def _prepare_results(
        self,
        results: list[SearchResult],
        query: str,
        include: list[str],
        exclude: list[str],
        *,
        sort_by_score: bool = True,
        relevance_queries: list[str] | None = None,
    ) -> list[SearchResult]:
        scoring_queries = relevance_queries or [query]
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
            item.preliminary_score = max(
                score_search_result(candidate_query, item) for candidate_query in scoring_queries
            )
            normalized.append(item)
        deduplicated = (
            deduplicate_results(normalized)
            if sort_by_score
            else _deduplicate_exact_results(normalized)
        )
        for item in deduplicated:
            item.preliminary_score = max(
                score_search_result(candidate_query, item) for candidate_query in scoring_queries
            )
        if not sort_by_score:
            return deduplicated
        return sorted(deduplicated, key=lambda item: item.preliminary_score, reverse=True)

    def _prioritize_fetchable_candidates(
        self,
        candidates: list[SearchResult],
        *,
        minimum: int,
        preserve_failed: set[str] | None = None,
    ) -> list[SearchResult]:
        healthy: list[SearchResult] = []
        browser_recoverable: list[SearchResult] = []
        recently_failed: list[SearchResult] = []
        preserved = preserve_failed or set()
        for candidate in candidates:
            if has_sensitive_query(candidate.url):
                healthy.append(candidate)
                continue
            key = self._page_key(candidate.url)
            failure = self.cache.get("failures", key)
            if not isinstance(failure, dict):
                healthy.append(candidate)
                continue
            page = self.cache.get("pages", key)
            extraction_failed = failure.get("stage") == "extraction"
            if not extraction_failed and isinstance(page, dict):
                healthy.append(candidate)
            elif _candidate_key(candidate) in preserved:
                browser_recoverable.append(candidate)
            else:
                recently_failed.append(candidate)
        prioritized = healthy + browser_recoverable
        return prioritized if len(prioritized) >= minimum else prioritized + recently_failed

    async def _retrieve(
        self,
        query: str,
        plan: QueryPlan,
        candidates: list[SearchResult],
        failures: list[dict[str, str]],
        *,
        browser_budget: int,
        relevance_queries: list[str],
        deadline_at: float | None,
        attempt_limit: int | None = None,
        preferred_by_query: dict[str, SearchResult] | None = None,
    ) -> tuple[list[tuple[SourceRecord, list[Passage]]], int]:
        requested_limit = len(candidates) if attempt_limit is None else attempt_limit
        hard_limit = min(len(candidates), requested_limit)
        if hard_limit <= 0:
            return [], 0
        fallback_budget = _BrowserFallbackBudget(browser_budget)
        retained: list[tuple[SourceRecord, list[Passage]]] = []
        seen_hashes: set[str] = set()
        attempted: set[str] = set()
        attempts = 0

        async def retrieve_batch(batch: list[tuple[SearchResult, str | None]]) -> None:
            nonlocal attempts
            if not batch:
                return
            first_index = attempts + 1
            for candidate, _ in batch:
                attempted.add(_candidate_key(candidate))
            attempts += len(batch)
            tasks = [
                asyncio.create_task(
                    self._retrieve_one(
                        query,
                        plan,
                        candidate,
                        first_index + offset,
                        browser_budget=fallback_budget,
                        relevance_queries=[
                            assigned_facet or _best_candidate_query(candidate, relevance_queries)
                        ],
                    )
                )
                for offset, (candidate, assigned_facet) in enumerate(batch)
            ]
            await _wait_until_deadline(tasks, deadline_at)
            for (candidate, _), task in zip(batch, tasks, strict=True):
                if task.cancelled():
                    failures.append(
                        {
                            "stage": "fetch_or_extract",
                            "url": redact_url(candidate.url),
                            "error": "ResearchDeadlineExceeded",
                        }
                    )
                    continue
                try:
                    response = task.result()
                except BaseException as exc:
                    failures.append(
                        {
                            "stage": "fetch_or_extract",
                            "url": redact_url(candidate.url),
                            "error": type(exc).__name__,
                        }
                    )
                    continue
                source, passages = response
                if source.content_hash in seen_hashes:
                    failures.append(
                        {
                            "stage": "deduplication",
                            "url": redact_url(candidate.url),
                            "error": "duplicate_content",
                        }
                    )
                    continue
                seen_hashes.add(source.content_hash)
                retained.append((source, passages))

        if len(relevance_queries) <= 1:
            await retrieve_batch([(candidate, None) for candidate in candidates[:hard_limit]])
            return retained, attempts

        preferred = preferred_by_query or {}
        while attempts < hard_limit:
            missing = _missing_retrieval_facets(relevance_queries, retained)
            remaining_slots = hard_limit - attempts
            batch: list[tuple[SearchResult, str | None]] = []
            if missing:
                for facet in missing:
                    if len(batch) >= remaining_slots:
                        break
                    match = _next_facet_candidate(
                        candidates,
                        facet,
                        attempted | {_candidate_key(item) for item, _ in batch},
                        preferred.get(facet),
                    )
                    if match is not None:
                        batch.append((match, facet))
            else:
                batch = [
                    (candidate, cast(str | None, None))
                    for candidate in candidates
                    if _candidate_key(candidate) not in attempted
                ][:remaining_slots]
            if not batch:
                fallback_count = min(remaining_slots, max(1, len(missing)))
                batch = [
                    (candidate, cast(str | None, None))
                    for candidate in candidates
                    if _candidate_key(candidate) not in attempted
                ][:fallback_count]
            if not batch:
                break
            await retrieve_batch(batch)
            if deadline_at is not None and time.monotonic() >= deadline_at:
                break
        return retained, attempts

    async def _retrieve_one(
        self,
        query: str,
        plan: QueryPlan,
        result: SearchResult,
        index: int,
        *,
        browser_budget: _BrowserFallbackBudget,
        relevance_queries: list[str],
    ) -> tuple[SourceRecord, list[Passage]]:
        if not await self._robots_allowed(result.url):
            raise FetchError("robots.txt disallows retrieval")
        page_key = self._page_key(result.url)
        request_sensitive = has_sensitive_query(result.url)
        fetched: FetchResult | None = None
        try:
            cached_failure = None if request_sensitive else self.cache.get("failures", page_key)
            if isinstance(cached_failure, dict) and cached_failure.get("stage") == "extraction":
                raise ExtractionError("recent cached extraction failure")
            fetched = await self._fetch_cached(result.url)
            page = self._extract_cached(fetched)
        except (FetchError, ExtractionError) as exc:
            fetch_sensitive = bool(
                fetched
                and (
                    has_sensitive_query(fetched.requested_url)
                    or has_sensitive_query(fetched.final_url)
                )
            )
            if isinstance(exc, ExtractionError) and not request_sensitive and not fetch_sensitive:
                self._cache_put(
                    "failures",
                    page_key,
                    {"error": type(exc).__name__, "stage": "extraction"},
                    minutes=5,
                )
            if not self.settings.enable_browser or not browser_budget.claim():
                raise
            try:
                fetched = await self.browser.fetch(result.url)
                page = self._extract_cached(fetched)
                browser_sensitive = (
                    request_sensitive
                    or has_sensitive_query(fetched.requested_url)
                    or has_sensitive_query(fetched.final_url)
                )
                if not browser_sensitive:
                    self._cache_put("pages", page_key, fetched.model_dump(mode="json"))
            except ExtractionError as browser_exc:
                browser_sensitive = request_sensitive or bool(
                    fetched
                    and (
                        has_sensitive_query(fetched.requested_url)
                        or has_sensitive_query(fetched.final_url)
                    )
                )
                if not browser_sensitive:
                    self._cache_put(
                        "failures",
                        page_key,
                        {"error": type(browser_exc).__name__, "stage": "extraction"},
                        minutes=5,
                    )
                raise
            if not request_sensitive:
                self.cache.delete("failures", page_key)
        passages = self.reranker.rank_for_queries(relevance_queries, chunk_text(page.text))[:8]
        absolute_relevance = _absolute_source_relevance(result, relevance_queries, passages)
        quality = 0.65 * result.preliminary_score + 0.35 * freshness_score(
            page.updated_at or page.published_at, time_sensitive=plan.time_sensitive
        )
        source = SourceRecord(
            source_id=f"src_{index:03d}",
            url=redact_url(page.url),
            title=_redact_possible_url(page.title),
            domain=urlsplit(page.url).hostname or result.domain,
            published_at=page.published_at,
            updated_at=page.updated_at,
            retrieved_at=page.retrieved_at,
            source_type=source_type(page.url),
            quality_score=round(quality, 4),
            quality_explanation=explain_source_quality(
                result,
                query=query,
                dated=bool(page.updated_at or page.published_at),
            ),
            relevance_score=absolute_relevance,
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
                "query_fingerprint": query_fingerprint(query),
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
        return await self._coalesce(
            self._search_inflight,
            key,
            lambda: self._search_uncached(
                key,
                query,
                language=language,
                recency_days=recency_days,
                limit=limit,
                allow_fallback=allow_fallback,
            ),
        )

    async def _search_uncached(
        self,
        key: str,
        query: str,
        *,
        language: str,
        recency_days: int | None,
        limit: int,
        allow_fallback: bool,
    ) -> list[SearchResult]:
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
        if results and not any(has_sensitive_query(result.url) for result in results):
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
        if has_sensitive_query(url):
            return await self.fetcher.fetch(url)
        key = self._page_key(url)
        cached = self.cache.get("pages", key)
        if isinstance(cached, dict):
            result = FetchResult.model_validate(cached)
            result.method = "cache"
            return result
        if self.cache.get("failures", key) is not None:
            raise FetchError("recent cached retrieval failure")
        return await self._coalesce(
            self._fetch_inflight,
            key,
            lambda: self._fetch_uncached(key, url),
        )

    async def _fetch_uncached(self, key: str, url: str) -> FetchResult:
        cached = self.cache.get("pages", key)
        if isinstance(cached, dict):
            result = FetchResult.model_validate(cached)
            result.method = "cache"
            return result
        if self.cache.get("failures", key) is not None:
            raise FetchError("recent cached retrieval failure")
        try:
            result = await self.fetcher.fetch(url)
        except FetchError as exc:
            self._cache_put(
                "failures",
                key,
                {"error": type(exc).__name__, "stage": "fetch"},
                minutes=5,
            )
            raise
        if has_sensitive_query(result.requested_url) or has_sensitive_query(result.final_url):
            return result
        self._cache_put("pages", key, result.model_dump(mode="json"))
        return result

    def _extract_cached(self, fetched: FetchResult) -> ExtractedPage:
        if has_sensitive_query(fetched.requested_url) or has_sensitive_query(fetched.final_url):
            return self.extractor.extract(fetched)
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
        key = Cache.key({"url": robots_url, "user_agent": user_agent, "policy_version": 2})
        cached = self.cache.get("robots", key)
        if isinstance(cached, bool):
            return cached
        if isinstance(cached, dict):
            body = cached.get("body")
            return True if not isinstance(body, str) else robots_allows(body, url, user_agent)
        body = await self._coalesce(
            self._robots_inflight,
            key,
            lambda: self._robots_uncached(key, robots_url),
        )
        return True if body is None else robots_allows(body, url, user_agent)

    async def _robots_uncached(self, key: str, robots_url: str) -> str | None:
        cached = self.cache.get("robots", key)
        if isinstance(cached, dict):
            body = cached.get("body")
            return body if isinstance(body, str) else None
        try:
            async with asyncio.timeout(self.settings.robots_timeout_seconds):
                result = await self.fetcher.fetch(robots_url)
        except (FetchError, TimeoutError):
            self._cache_put("robots", key, {"body": None}, minutes=5)
            return None
        self._cache_put("robots", key, {"body": result.body}, minutes=360)
        return result.body

    async def _coalesce(
        self,
        registry: dict[str, _Flight],
        key: str,
        operation: Callable[[], Coroutine[Any, Any, _T]],
    ) -> _T:
        flight = registry.get(key)
        if flight is None:
            flight = _Flight(asyncio.create_task(operation()))
            registry[key] = flight
        flight.waiters += 1
        try:
            return cast(_T, await asyncio.shield(flight.task))
        finally:
            flight.waiters -= 1
            if flight.waiters == 0:
                if registry.get(key) is flight:
                    registry.pop(key, None)
                if not flight.task.done():
                    flight.task.cancel()
                await asyncio.gather(flight.task, return_exceptions=True)

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


async def _wait_until_deadline(tasks: list[asyncio.Task[Any]], deadline_at: float | None) -> None:
    if not tasks:
        return
    try:
        timeout = None if deadline_at is None else max(0.0, deadline_at - time.monotonic())
        _, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    except asyncio.CancelledError:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def _interleave_results(groups: list[list[SearchResult]]) -> list[SearchResult]:
    merged: list[SearchResult] = []
    for rank in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if rank >= len(group):
                continue
            item = group[rank].model_copy(deep=True)
            item.rank = len(merged) + 1
            merged.append(item)
    return merged


def _plan_compound_query(
    planner: HeuristicQueryPlanner,
    original: str,
    facets: list[str],
    limit: int,
) -> QueryPlan:
    subplans = [planner.plan(facet, 8) for facet in facets]
    expansions: list[str] = []
    for subplan in subplans:
        lowered = subplan.original.casefold()
        marker = (
            "current release notes"
            if subplan.time_sensitive
            else "issue tracker"
            if re.search(r"\b(?:error|exception|failed|traceback)\b", lowered)
            else "specification benchmark"
            if re.search(r"\b(?:compare|versus|vs\.?|difference|better)\b", lowered)
            else "official documentation"
        )
        choices = [
            query for query in subplan.queries if query.casefold() != subplan.original.casefold()
        ]
        preferred = next((query for query in choices if marker in query.casefold()), None)
        if preferred or choices:
            expansions.append(preferred or choices[0])
    return QueryPlan(
        original=original,
        queries=_unique_queries([*facets, *expansions])[:limit],
        topics=facets,
        time_sensitive=any(subplan.time_sensitive for subplan in subplans),
    )


def _ranking_queries(plan: QueryPlan, fallback: str) -> list[str]:
    topics = [topic for topic in plan.topics if len(meaningful_tokens(topic)) >= 2]
    if len(topics) <= 1:
        return [fallback]
    anchors = distinctive_query_tokens(fallback)
    ordered_anchors = [
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9./_-]+", fallback)
        if token.casefold() in anchors
    ]
    contextualized = []
    for topic in topics:
        topic_anchors = anchors & set(meaningful_tokens(topic))
        if topic_anchors or not _facet_needs_anchor_context(topic):
            contextualized.append(topic)
        else:
            contextualized.append(" ".join([*ordered_anchors, topic]))
    return _unique_queries(contextualized)[:4]


def _facet_needs_anchor_context(topic: str) -> bool:
    if re.search(
        r"\b(?:it|its|itself|they|their|them|those|these|former|latter|same|such)\b",
        topic,
        re.IGNORECASE,
    ):
        return True
    if not re.match(
        r"^(?:(?:what|which)\s+(?:is|are|was|were|does|do)|how\s+many)\b",
        topic.strip(),
        re.IGNORECASE,
    ):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z0-9.+#-]*", topic)
    question_words = {"how", "what", "which"}
    named_subject = any(
        word.casefold() not in question_words
        and (word.isupper() or (word[0].isupper() and not word.islower()))
        for word in words[1:]
    )
    return not named_subject


def _is_query_aligned_primary(query: str, result: SearchResult) -> bool:
    kind = source_type(result.url)
    if kind not in {"official_documentation", "primary_institution", "source_repository"}:
        return False
    query_terms = set(meaningful_tokens(query))
    content = f"{result.title} {result.snippet}"
    matched_terms = query_terms & set(meaningful_tokens(content))
    if len(matched_terms) < min(2, len(query_terms)):
        return False
    generic_intent_terms = {
        "documentation",
        "find",
        "github",
        "official",
        "page",
        "reference",
        "repository",
        "source",
        "website",
    }
    subject_terms = query_terms - generic_intent_terms
    if subject_terms and not subject_terms & matched_terms:
        return False
    anchors = distinctive_query_tokens(query)
    if anchors and distinctive_anchor_coverage(query, content) <= 0.0:
        return False
    score = score_search_result(query, result)
    if domain_matches_authority(query, result.url):
        return score >= 0.30
    return kind == "primary_institution" and score >= 0.55


def _absolute_source_relevance(
    result: SearchResult, queries: list[str], passages: list[Passage]
) -> float:
    if not passages:
        return 0.0
    best_score = 0.0
    for query in queries or [""]:
        terms = set(meaningful_tokens(query))
        if not terms:
            continue
        anchors = distinctive_query_tokens(query)
        required_coverage = 1.0 if len(terms) <= 2 else 0.34
        for passage in passages:
            passage_text = f"{passage.heading or ''} {passage.text}"
            passage_terms = set(meaningful_tokens(passage_text))
            coverage = len(terms & passage_terms) / max(1, len(terms))
            if coverage < required_coverage:
                continue
            anchor_coverage = distinctive_anchor_coverage(query, passage_text) if anchors else 0.0
            if anchors and anchor_coverage <= 0.0:
                continue
            prior_lift = result.preliminary_score * min(1.0, coverage / 0.60)
            score = 0.70 * coverage + 0.20 * prior_lift + 0.10 * anchor_coverage
            best_score = max(best_score, score)
    return round(min(1.0, best_score), 4)


def _domain_matches(domain: str, patterns: Iterable[str]) -> bool:
    normalized = domain.lower().rstrip(".")
    return any(
        normalized == pattern.lower().lstrip(".")
        or normalized.endswith(f".{pattern.lower().lstrip('.')}")
        for pattern in patterns
    )


def _redact_possible_url(value: str) -> str:
    return redact_url(value) if urlsplit(value).scheme in {"http", "https"} else value


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
                url=redact_url(candidate.url),
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


def _select_fetch_candidates(
    candidates: list[SearchResult],
    limit: int,
    *,
    relevance_queries: list[str] | None = None,
    preferred_candidates: list[SearchResult] | None = None,
) -> list[SearchResult]:
    if limit <= 0:
        return []
    selected: list[SearchResult] = []
    for candidate in preferred_candidates or []:
        if _candidate_key(candidate) not in {_candidate_key(item) for item in selected}:
            selected.append(candidate)
        if len(selected) >= limit:
            return selected
    facet_reserve = 2 if relevance_queries and limit >= 2 * len(relevance_queries) else 1
    facet_rankings: dict[str, list[SearchResult]] = {}
    for query in relevance_queries or []:
        query_terms = set(meaningful_tokens(query))
        required_overlap = min(2, len(query_terms))
        facet_rankings[query] = sorted(
            (
                candidate
                for candidate in candidates
                if len(
                    query_terms & set(meaningful_tokens(f"{candidate.title} {candidate.snippet}"))
                )
                >= required_overlap
            ),
            key=lambda candidate: score_search_result(query, candidate),
            reverse=True,
        )
    for _ in range(facet_reserve):
        for query in relevance_queries or []:
            ranked_for_facet = facet_rankings[query]
            best_score = (
                score_search_result(query, ranked_for_facet[0]) if ranked_for_facet else 0.0
            )
            match = next(
                (
                    candidate
                    for candidate in ranked_for_facet
                    if _candidate_key(candidate) not in {_candidate_key(item) for item in selected}
                    and score_search_result(query, candidate) >= max(0.12, best_score * 0.55)
                ),
                None,
            )
            if match is None:
                continue
            selected.append(match)
            if len(selected) >= limit:
                return selected
    if candidates and _candidate_key(candidates[0]) not in {
        _candidate_key(item) for item in selected
    }:
        selected.append(candidates[0])
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
            and _candidate_key(candidate) not in {_candidate_key(item) for item in selected}
        ),
        None,
    )
    if primary is not None:
        selected.append(primary)
    for candidate in eligible:
        if len(selected) >= limit:
            break
        if _candidate_key(candidate) not in {
            _candidate_key(item) for item in selected
        } and candidate.domain not in {item.domain for item in selected}:
            selected.append(candidate)
    for candidate in candidates:
        if len(selected) >= limit:
            break
        if _candidate_key(candidate) not in {_candidate_key(item) for item in selected}:
            selected.append(candidate)
    return selected


def _candidate_key(candidate: SearchResult) -> str:
    return candidate.canonical_url or candidate.url


def _preferred_exact_candidates(
    exact_candidates: list[SearchResult], queries: list[str]
) -> dict[str, SearchResult]:
    """Associate each facet with its interleaved exact rank-one candidate."""
    available = list(exact_candidates[: len(queries)])
    preferred: dict[str, SearchResult] = {}
    for query in queries:
        if not available:
            break
        terms = set(meaningful_tokens(query))
        required_overlap = min(2, len(terms))
        eligible = [
            candidate
            for candidate in available
            if len(terms & set(meaningful_tokens(f"{candidate.title} {candidate.snippet}")))
            >= required_overlap
        ]
        if not eligible:
            continue
        best = max(eligible, key=lambda candidate: score_search_result(query, candidate))
        if score_search_result(query, best) < 0.12:
            continue
        preferred[query] = best
        available.remove(best)
    return preferred


def _best_candidate_query(candidate: SearchResult, queries: list[str]) -> str:
    if not queries:
        return ""
    return max(queries, key=lambda query: score_search_result(query, candidate))


def _missing_retrieval_facets(
    queries: list[str], ranked: list[tuple[SourceRecord, list[Passage]]]
) -> list[str]:
    passages = [
        passage
        for _, source_passages in ranked
        for passage in source_passages
        if assess_injection(passage.text).risk != "high"
    ]
    missing: list[str] = []
    for query in queries:
        terms = set(meaningful_tokens(query))
        required = 1.0 if len(terms) <= 2 else 0.60
        best = max(
            (
                len(terms & set(meaningful_tokens(passage.text))) / max(1, len(terms))
                for passage in passages
            ),
            default=0.0,
        )
        if best < required:
            missing.append(query)
    return missing


def _next_facet_candidate(
    candidates: list[SearchResult],
    query: str,
    attempted: set[str],
    preferred: SearchResult | None,
) -> SearchResult | None:
    if preferred is not None and _candidate_key(preferred) not in attempted:
        return preferred
    query_terms = set(meaningful_tokens(query))
    for required_overlap in (min(2, len(query_terms)), 1):
        eligible = [
            (position, candidate)
            for position, candidate in enumerate(candidates)
            if _candidate_key(candidate) not in attempted
            and len(query_terms & set(meaningful_tokens(f"{candidate.title} {candidate.snippet}")))
            >= required_overlap
        ]
        if eligible:
            return max(
                eligible,
                key=lambda item: (
                    score_search_result(query, item[1]),
                    item[1].preliminary_score,
                    -item[0],
                ),
            )[1]
    return None


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
