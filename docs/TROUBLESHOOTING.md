# Troubleshooting

Run `.\scripts\doctor.ps1` first.

## Docker or startup

```powershell
docker compose config
docker compose ps
docker compose logs --tail 200 app tor-search tor-fetch
```

`uv` is not required on the host. Docker Desktop must be running Linux containers. A generated `SEARXNG_SECRET` must exist in `.env`.

The loopback MCP bridge follows app-container IP changes automatically. If the endpoint becomes unhealthy after an app replacement, inspect `docker compose logs mcp-bridge` and verify the bridge still has only `internal_private` plus `host_loopback`; do not connect it to an egress network as a workaround.

## Search failures

Check `search_status`. Search proxy and SearXNG failures are distinct. SearXNG container logs are deliberately disabled because engine errors can include query URLs. Engine CAPTCHA/rate-limit failures are expected occasionally; the pipeline rotates queries but does not bypass CAPTCHAs. If Tor is down, failure is intentional and direct egress is never tried.

LM Studio error `-32001` means its MCP client stopped waiting before the research server finished. Use the canonical `http://127.0.0.1:8088/mcp/` URL and set `"timeout": 900000` on the `private-research` entry in `mcp.json`. This is an outer transport timeout; interactive search tools return their best completed evidence within 105 seconds. That cap does not weaken the 30-second per-I/O-attempt limit, the 60-second retried page-fetch bound, the separate 15-second robots wrapper, or the longer 90/240/720-second deadlines available to direct pipeline/benchmark runs.

If the tool reports completion but the model produces no answer, first reload the MCP integration and call `search_status`. `interactive_limits` should report a 105-second deadline, a five-second repeat-search cooldown, and 8,000/9,000/10,000-character Quick/Standard/Deep budgets. The compact result tells the model to answer immediately and not call another search tool in the same turn. The server also suppresses an immediate duplicate or parallel search with a tiny control response; together these controls avoid accumulating multiple large tool results until no generation context remains.

## Fetch/extraction failures

Unsupported/binary/archive content, unsafe URLs, redirects into internal ranges, timeouts, oversized responses, and pages with insufficient main text are explicit failures. Enable browser fallback only with `--profile browser` and `PRM_ENABLE_BROWSER=true`; it remains budgeted and isolated.

## Database

```powershell
docker compose exec -T app python -c "from app.runtime import create_runtime; print(create_runtime().database.integrity())"
```

Stop the stack before copying the volume. Expired rows are safe to remove; unrelated host files are never deletion targets.

## Privacy failure

Do not use the stack for sensitive research until `.\scripts\privacy-test.ps1` passes. Inspect container networks and port mappings. Never solve a failure by connecting app/SearXNG/browser directly to an egress network.
