# Architecture

The system has six replaceable layers: deterministic planning, URL discovery, private retrieval, extraction, local ranking, and evidence analysis. `ResearchPipeline` coordinates interfaces rather than calling LM Studio. SearXNG is only a `SearchBackend`; an alternative backend can implement the same protocol.

Retrieval checks a same-origin `robots.txt` through the fetch Tor route, then tries bounded HTTP and extraction in this order: Trafilatura, Selectolax main/article text, Readability. A disallow rule is honored; an unavailable robots file is treated as no published rule. Playwright is a separately isolated, disabled-by-default last resort. Page hashes remove duplicate copies. BM25-like lexical ranking is always available; local model integration is optional and requires preinstalled files.

SQLite uses WAL plus FTS5. Search responses, pages, evidence, and failure states have independent namespaces. Search history and useful short-term caching are separate controls.

Evidence IDs are assigned only after prompt-injection screening. A citation includes its source/evidence IDs; structured records retain URL, title, passage, heading, offsets, retrieval time, and content hash. Offsets are character offsets into extracted text, never invented webpage line numbers.

The exact user query is always searched first for up to 10 results. Safe-normalized results retain SearXNG order and are stored as unverified `search_snippets` with their original rank; only canonical-URL duplicates are removed. This immutable floor is scanned for prompt injection, with high-risk title/snippet text redacted before return, and survives even if every robots check, page fetch, or extraction fails. Expanded queries are additive and cannot evict exact-query snippets.

Search results are cached only when at least one result is present. Exact-query misses are not silently replaced; expanded-query misses may be retried once with a deterministic entity-focused query and remain uncached so a transient engine CAPTCHA or rate limit cannot poison later research modes. In strict mode, cache misses are serialized and spaced before reaching SearXNG so expanded queries do not exhaust several engines through one Tor exit. Deep query and round budgets scale with the requested source count and stop when discovery has enough primary-source candidates. Fetch selection always retains the highest-ranked candidate and applies primary-source/domain diversity only within a relevance threshold. Retrieved passages are reranked globally and low-value candidates are removed before source-diverse evidence IDs are assigned.

SearXNG keeps several independent general engines enabled and adds the `it`, `science`, or `news` vertical only when deterministic query signals call for it. Engine suspension windows are bounded so a rotated Tor exit can recover without retaining a day-long CAPTCHA/access-denied state; requests remain paced in the app and there is no CAPTCHA bypass.

## Request flow

1. Validate MCP input and choose a quality-first automatic or explicit budget.
2. Search the exact question for the immutable top-10 snippet floor.
3. Decompose/expand the question without an LLM callback and search variants through paced internal SearXNG.
4. Normalize URLs, remove tracking parameters, deduplicate expansions, and pre-rank.
5. Fetch selected pages through `tor-fetch`, validating every redirect.
6. Extract metadata/main text; hash and semantically chunk it.
7. Rank passages, quarantine injection-like instructions, build citations.
8. Report coverage, primary-source presence, gaps, failures, and contradictions.
9. Return structured JSON containing both unverified snippets and verified extracted evidence. Final prose synthesis remains the calling model's job.
