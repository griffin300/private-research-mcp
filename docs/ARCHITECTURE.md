# Architecture

The system has six replaceable layers: deterministic planning, URL discovery, private retrieval, extraction, local ranking, and evidence analysis. `ResearchPipeline` coordinates interfaces rather than calling LM Studio. SearXNG is only a `SearchBackend`; an alternative backend can implement the same protocol.

Retrieval checks a same-origin `robots.txt` through the fetch Tor route, then tries bounded HTTP and extraction in this order: Trafilatura, Selectolax main/article text, Readability. A disallow rule is honored; an unavailable robots file is treated as no published rule. Playwright is a separately isolated, disabled-by-default last resort. Page hashes remove duplicate copies. BM25-like lexical ranking is always available; local model integration is optional and requires preinstalled files.

SQLite uses WAL plus FTS5. Search responses, pages, evidence, and failure states have independent namespaces. Search history and useful short-term caching are separate controls.

Evidence IDs are assigned only after prompt-injection screening. A citation includes its source/evidence IDs; structured records retain URL, title, passage, heading, offsets, retrieval time, and content hash. Offsets are character offsets into extracted text, never invented webpage line numbers.

Search results are cached only when at least one result is present. An empty response is retried once with a deterministic entity-focused query and remains uncached so a transient engine CAPTCHA or rate limit cannot poison later research modes. In strict mode, cache misses are serialized and spaced before reaching SearXNG so expanded queries do not exhaust several engines through one Tor exit. Deep query and round budgets scale with the requested source count and stop when discovery has enough primary-source candidates. Retrieved passages are reranked globally and selected with source-diversity and near-duplicate penalties before evidence IDs are assigned.

## Request flow

1. Validate MCP input and choose a deterministic budget.
2. Decompose/expand the question without an LLM callback.
3. Search variants concurrently through internal SearXNG.
4. Normalize URLs, remove tracking parameters, deduplicate, and pre-rank.
5. Fetch selected pages through `tor-fetch`, validating every redirect.
6. Extract metadata/main text; hash and semantically chunk it.
7. Rank passages, quarantine injection-like instructions, build citations.
8. Report coverage, primary-source presence, gaps, failures, and contradictions.
9. Return structured JSON. Final prose synthesis remains the calling model's job.
