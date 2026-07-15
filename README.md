# Private Research MCP

`private-research-mcp` is a local evidence engine for LM Studio. It expands a question into focused queries, discovers URLs through SearXNG, retrieves pages through a separate Tor path, extracts main content, ranks passages locally, and returns exact citation targets. It does not synthesize an answer or substitute model memory when retrieval fails.

Compared with a raw SearXNG MCP wrapper, it adds full-page retrieval, URL/content deduplication, source and passage ranking, freshness handling, coverage analysis, contradiction signals, prompt-injection quarantine, SSRF controls, caching, and evidence-level citations.

## Status

The core, Docker topology, MCP transports, tests, scripts, benchmark harness, and documentation are implemented. The release-blocking Docker privacy suite and live MCP search/read probes passed on the development host. Optional embeddings and browser fallback remain disabled by default.

Known limits: the lexical BM25-like ranker is the active production path; FastEmbed/cross-encoder model provisioning and hybrid-score integration are not complete. The 50-question benchmark framework is complete, but only a one-question four-mode smoke run was executed during this build. The optional browser image and Tor route were live-tested but remain opt-in.

## Architecture

```text
LM Studio ──localhost──> FastMCP /mcp ─┐
                                      ├─ heuristic query planner
Dashboard ─localhost──> FastAPI ──────┤
                                      ├─ SearXNG ──SOCKS/DNS──> tor-search ─> web search engines
                                      ├─ HTTP extractor ───────> tor-fetch  ─> destination pages
                                      ├─ optional Playwright ──> tor-fetch
                                      └─ SQLite FTS5 + local rankers ─> evidence package

app, SearXNG, and browser: internal_private (internal: true) only
loopback bridge: internal_private + no-masquerade host_loopback
tor-search: internal_private + egress_search
tor-fetch:  internal_private + egress_fetch
```

The host publishes only `127.0.0.1:8088` through a TCP sidecar. The app remains attached solely to the internal network and listens on `0.0.0.0` *inside that isolated network*. The sidecar installs a namespace-local default-deny egress firewall, permits only app traffic and established replies, then drops to UID 10001. Its host bridge also has IP masquerading disabled.

## Requirements

- Windows 10/11 with Docker Desktop and Compose
- PowerShell 7 recommended (Windows PowerShell 5.1 is supported)
- At least 3 GB free memory for the default stack; more if browser/ranking models are enabled
- LM Studio 0.3.17 or newer for MCP host support

## Setup

From this repository:

```powershell
.\scripts\setup.ps1
```

This preserves an existing `.env`, generates a SearXNG secret when needed, builds and starts the stack, runs an MCP smoke test, and runs release-blocking privacy checks. No ranking model is downloaded unless explicitly requested. The default lexical ranker is fully functional.

Common commands:

```powershell
.\scripts\start.ps1
.\scripts\stop.ps1
.\scripts\doctor.ps1
.\scripts\run-tests.ps1
.\scripts\privacy-test.ps1
.\scripts\run-benchmark.ps1
```

## LM Studio MCP setup

1. Run `.\scripts\setup.ps1` and wait for the privacy checks.
2. In LM Studio, open the **Program** tab, choose **Install → Edit mcp.json**.
3. Add this entry inside `mcpServers`:

```json
{
  "mcpServers": {
    "private-research": {
      "url": "http://127.0.0.1:8088/mcp"
    }
  }
}
```

4. Save, enable the server, and ask the model to call `search_status`.

For LM Studio API clients, enable **Allow calling servers from mcp.json** (LM Studio requires authentication for that setting), then reference `mcp/private-research` as an integration. See `docs/MCP_SETUP.md` for stdio, API, and troubleshooting details.

## MCP tools and examples

- `search_web`: quick/standard/deep evidence search with deterministic budgets.
- `deep_research`: multiple rounds, gaps, contradictions, source quality, unresolved questions.
- `read_url`: safe retrieval and question-aware passage ranking for one URL.
- `search_status`: component health and unsafe-fallback state.
- `clear_local_data`: deletes only project data and requires `confirm: true`.

Example arguments:

```json
{"query":"What changed in Python MCP SDK 1.28?","mode":"standard","max_sources":8,"recency_days":90,"include_domains":["github.com"],"exclude_domains":[],"language":"en"}
```

Quick uses up to 3 queries/5 pages/10 passages. Standard uses up to 6 queries/10 pages/20 passages and a gap round. Deep uses up to 15 queries/25 pages/40 passages and contradiction analysis. Query, result, page, passage, round, and browser budgets are bounded settings exposed as `PRM_QUICK_*`, `PRM_STANDARD_*`, and `PRM_DEEP_*` variables.

## Configuration

Copy `.env.example` to `.env` only if setup has not done so. Important defaults:

```env
PRM_PRIVACY_MODE=strict
PRM_DIRECT_EGRESS_ALLOWED=false
PRM_STORE_SEARCH_HISTORY=false
PRM_LOG_RAW_QUERIES=false
PRM_ENABLE_EMBEDDINGS=false
PRM_ENABLE_RERANKER=false
PRM_ENABLE_BROWSER=false
```

Strict mode refuses missing/shared proxies and never retries directly. `development` mode must be explicit and is not used by Docker Compose. An existing SearXNG can be selected with `PRM_SEARXNG_BASE_URL`, but it must still be reachable within the privacy topology for strict deployment.

The optional enhanced planner accepts only a separate loopback/private/Docker-internal OpenAI-compatible endpoint. It falls back to deterministic planning on failure and rejects reuse of the primary LM Studio endpoint.

## Privacy guarantees and limitations

The Compose topology blocks direct app/SearXNG/browser egress and uses distinct Tor containers for search and fetch. SOCKS hostname resolution avoids local destination DNS. Queries and cookies are not persisted by default; browser contexts are ephemeral. No telemetry or cloud API is configured.

Tor is not perfect anonymity. Timing correlation, malicious exits, identifiable queries, destination authentication, browser fingerprinting, compromised dependencies/host, and a hostile local Docker daemon remain risks. Search engines see a search Tor exit; destination sites see a different fetch Tor exit. See `docs/THREAT_MODEL.md` and `docs/PRIVACY.md`.

## Data and deletion

SQLite and caches live in the `research-data` Docker volume. The normal log stream contains opaque request IDs, not raw queries. Call `clear_local_data` with `confirm: true` or remove project data and the volume explicitly:

```powershell
docker compose down
docker volume rm private-research-mcp_research-data
```

The second command is intentionally not part of `stop.ps1`.

## Benchmarking

`.\scripts\run-benchmark.ps1` evaluates 50 questions against raw SearXNG, quick, standard, and deep modes. It writes `benchmarks/results/latest-report.md`, raw JSON, and a human-review template. It does not invent answer-quality scores.

The dashboard at `http://127.0.0.1:8088/dashboard` shows component health, cache activity, storage, recent opaque request metrics, coverage, and the last recorded privacy-suite result. It never displays raw queries by default.

## Troubleshooting

- `search backend unavailable`: inspect `docker compose logs searxng tor-search`.
- `fetch failed without direct fallback`: inspect `docker compose logs tor-fetch app`; direct fallback is intentionally absent.
- LM Studio does not list tools: confirm the stack is healthy and the URL ends in `/mcp`.
- `uv` missing on the host: use the Docker-backed scripts; host `uv` is optional.
- Engine CAPTCHA: SearXNG reports per-engine failures; the planner tries alternative queries, not CAPTCHA bypass.

See `docs/TROUBLESHOOTING.md` for diagnostic commands.

## License

MIT. Bundled services and dependencies retain their own licenses.
