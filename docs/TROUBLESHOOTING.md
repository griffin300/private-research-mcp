# Troubleshooting

Run `.\scripts\doctor.ps1` first.

## Docker or startup

```powershell
docker compose config
docker compose ps
docker compose logs --tail 200 app searxng tor-search tor-fetch
```

`uv` is not required on the host. Docker Desktop must be running Linux containers. A generated `SEARXNG_SECRET` must exist in `.env`.

## Search failures

Check `search_status`. Search proxy and SearXNG failures are distinct. SearXNG engine CAPTCHA/rate-limit failures are expected occasionally; the pipeline rotates queries but does not bypass CAPTCHAs. If Tor is down, failure is intentional and direct egress is never tried.

## Fetch/extraction failures

Unsupported/binary/archive content, unsafe URLs, redirects into internal ranges, timeouts, oversized responses, and pages with insufficient main text are explicit failures. Enable browser fallback only with `--profile browser` and `PRM_ENABLE_BROWSER=true`; it remains budgeted and isolated.

## Database

```powershell
docker compose exec -T app python -c "from app.runtime import create_runtime; print(create_runtime().database.integrity())"
```

Stop the stack before copying the volume. Expired rows are safe to remove; unrelated host files are never deletion targets.

## Privacy failure

Do not use the stack for sensitive research until `.\scripts\privacy-test.ps1` passes. Inspect container networks and port mappings. Never solve a failure by connecting app/SearXNG/browser directly to an egress network.
