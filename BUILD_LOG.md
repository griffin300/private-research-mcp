# Build log

## 2026-07-14 — Initial assumptions

- The repository is created at `private-research-mcp/`; no files outside it will be modified.
- Python 3.12 is authoritative even though the host currently exposes Python 3.14.
- The stable MCP Python SDK line is pinned (`mcp==1.28.1`); v2 is prerelease as of this build.
- Streamable HTTP is the preferred container transport; a stdio bridge is included for LM Studio.
- Strict mode is fail-closed: separate Tor gateways are mandatory and direct egress is rejected.
- The application never calls the primary LM Studio model during ordinary searches.
- Optional embedding/reranking code activates only when explicitly enabled and local files exist.
- Live privacy claims are withheld until the Docker privacy tests execute successfully.

## 2026-07-14 — Setup correction

- Initial host execution found Docker Desktop stopped and PowerShell 5.1 lacking `RandomNumberGenerator.Fill`.
- Setup now checks native Docker exit codes, uses the PowerShell 5.1-compatible RNG instance API, and repairs a partially created `.env` without overwriting existing values.

## 2026-07-14 — First local test run

- Python compilation passed and the dependency lock resolved with Python 3.12.
- Initial pytest: 31 passed, 2 failed, 2 errored (sandbox temp ACL). The failures exposed HTML-comment retention and an unrecognized prompt-injection phrase variant.
- Corrected comment stripping and broadened the instruction-override detector; redirected tool caches to project-local ignored storage.

## 2026-07-14 — Resume after host interruption

- Workspace and dependency environment were intact; Ruff and Mypy remained clean.
- Connected search/page/extraction/evidence caches to the pipeline and added automatic retention cleanup plus FTS evidence indexing.
- Deep research now guarantees multiple distinct rounds within the configured total query budget.
- Added per-domain concurrency limits and a short circuit breaker without introducing any direct-network fallback.

## 2026-07-14 — First Docker startup correction

- Images built successfully, but both Tor gateways restarted because Compose mounted `/var/lib/tor` with the wrong numeric ownership.
- Confirmed the image's `debian-tor` identity is UID 100/GID 101 and corrected both tmpfs mounts.
- Setup, doctor, and privacy scripts previously tolerated failed native commands under Windows PowerShell 5.1; required checks now propagate nonzero exit codes and cannot print setup success after a failed start.

## 2026-07-14 — Loopback bridge correction

- Docker Desktop does not create an effective host port for containers attached only to an internal network, so a minimal localhost ingress sidecar was added while the app remains internal-only.
- The initial no-masquerade bridge still had effective Docker Desktop egress; the privacy test caught it.
- The sidecar now installs a namespace-local default-deny OUTPUT policy allowing only established replies and TCP to the app, then drops to UID 10001.

## 2026-07-14 — Live acceptance verification

- Docker Compose built and started the app, SearXNG, two Tor gateways, and loopback bridge successfully.
- The release privacy script passed topology, direct-IP egress, direct DNS, distinct Tor exits, raw-query logging, cloud-domain configuration, loopback bridge egress, fail-closed Tor shutdown, and recovery checks.
- Streamable HTTP MCP initialization listed all five required tools and returned structured status content.
- Live MCP `search_web` returned 10 extracted evidence passages; live `read_url` returned 3 ranked passages.
- A one-question benchmark smoke completed raw, quick, standard, and deep modes without errors. The 50-question corpus and human-review template are present; the full 200-run evaluation was not executed during this build.

## 2026-07-14 — Acceptance audit corrections

- Search/query/page/passage/round/browser budgets are environment-configurable and browser fallback obeys the per-mode budget.
- The optional enhanced planner calls only a separately configured local endpoint and deterministically falls back on failure.
- Retrieval honors available `robots.txt` rules through the fetch Tor route without weakening privacy when a robots file is unavailable.
- Request metrics, cache hit rate, and the last privacy-suite result are visible on the localhost dashboard without storing raw queries.
- Local FastEmbed/cross-encoder model provisioning remains intentionally incomplete: lexical ranking is production-functional, but the download manifest is disabled until exact model revisions and file hashes are reviewed.

## 2026-07-14 — Optional browser verification and final regression

- Corrected the Playwright image so Chromium is installed at `/ms-playwright` and readable by the non-root UID 10001 service account.
- Built and started the optional browser profile, confirmed its only network is `internal_private`, blocked its direct public IP and DNS access, and completed a real Chromium render reported as Tor through `tor-fetch`.
- The final local quality run passed Ruff formatting/linting, strict Mypy for 60 source files, and 44 Pytest unit/integration/security/privacy-static tests.
- The final live privacy run, with the browser profile active, passed every check including browser isolation, distinct Tor exits, fail-closed transport shutdown, and recovery.
