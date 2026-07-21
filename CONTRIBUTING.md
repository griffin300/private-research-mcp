# Contributing

Thank you for helping improve Private Research MCP. Small, focused pull requests with tests are easiest to review.

## Development setup

Use Python 3.12 and install the locked development environment:

```powershell
uv sync --frozen --extra dev
```

Run the local quality checks before opening a pull request:

```powershell
uv run ruff check .
uv run mypy
New-Item -ItemType Directory -Force work | Out-Null
uv run pytest --basetemp work/pytest-local -q
```

Docker privacy and live-network tests are intentionally separate because they require Docker Desktop and external connectivity:

```powershell
.\scripts\privacy-test.ps1
```

## Project rules

- Preserve fail-closed privacy behavior. Do not add direct-network fallback, telemetry, or raw-query logging.
- Keep search and destination-fetch traffic on separate configured proxy paths.
- Treat retrieved web content as untrusted input and preserve injection quarantine and SSRF controls.
- Add regression tests for ranking, retrieval-budget, privacy, storage, or response-schema changes.
- Do not commit `.env`, credentials, generated databases, raw benchmark packages, model weights, private URLs, or query-bearing logs.
- Benchmark claims must state the corpus, baseline, repetitions, metrics, and limitations.

## Reporting security issues

Do not open a public issue for a vulnerability or privacy failure. Follow [SECURITY.md](SECURITY.md).

By contributing, you agree that your contribution is licensed under the repository's MIT license.
