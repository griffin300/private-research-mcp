from __future__ import annotations

import html
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.runtime import Runtime


def create_dashboard_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()

    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard() -> str:
        status = await runtime.pipeline.status()
        stats = runtime.database.stats()
        cache_stats = runtime.pipeline.cache.stats()
        recent = runtime.database.recent_requests()
        privacy = _privacy_status(runtime)
        components = "".join(
            f"<li><code>{html.escape(name)}</code>: "
            f"{html.escape(str(details.get('status', 'unknown')))}</li>"
            for name, details in status.components.items()
        )
        rows = "".join(
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(item[key]))}</td>"
                for key in (
                    "request_id",
                    "duration_ms",
                    "queries_generated",
                    "raw_results",
                    "pages_fetched",
                    "extraction_failures",
                    "browser_fallbacks",
                    "source_count",
                    "evidence_count",
                    "coverage_score",
                )
            )
            + "</tr>"
            for item in recent
        )
        if not rows:
            rows = "<tr><td colspan='10'>No recorded requests.</td></tr>"
        status_class = "ok" if status.status == "healthy" else "warn"
        return f"""<!doctype html><html><head><meta charset='utf-8'><title>Private Research</title>
<style>body{{font:15px system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem;background:#111827;color:#e5e7eb}}code,a{{color:#93c5fd}}.ok{{color:#86efac}}.warn{{color:#fde68a}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #374151;padding:.45rem;text-align:left}}button{{padding:.5rem}}</style></head>
<body><h1>Private Research MCP</h1><p class='{status_class}'>Status: {status.status}</p>
<p>Privacy mode: <code>{status.privacy_mode}</code>; unsafe fallback: <code>{status.unsafe_fallback_enabled}</code>; last live privacy suite: <code>{html.escape(privacy)}</code></p>
<p>Cache entries: {stats["cache_entries"]} &middot; hits: {cache_stats["hits"]} &middot; misses: {cache_stats["misses"]} &middot; hit rate: {cache_stats["hit_rate"]} &middot; storage: {stats["bytes"]} bytes</p>
<h2>Components</h2><ul>{components}</ul>
<h2>Recent opaque requests</h2><table><thead><tr><th>ID</th><th>ms</th><th>queries</th><th>raw</th><th>pages</th><th>failures</th><th>browser</th><th>sources</th><th>evidence</th><th>coverage</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Local controls</h2><form method='post' action='/admin/clear?confirm=true'><button type='submit'>Clear local caches and history</button></form>
<p>Health: <a href='/health'>JSON status</a>. Privacy checks require Docker-host access: <code>.\\scripts\\privacy-test.ps1</code>.</p>
<p>Raw queries remain hidden unless persistence is explicitly enabled.</p></body></html>"""

    @router.post("/admin/clear")
    async def clear(confirm: bool = False) -> dict[str, object]:
        if not confirm:
            raise HTTPException(status_code=400, detail="confirm=true is required")
        return {
            "cleared": True,
            "rows": runtime.database.clear(
                ["search", "pages", "extracted", "robots", "evidence", "failures", "history"]
            ),
        }

    return router


def _privacy_status(runtime: Runtime) -> str:
    path = runtime.settings.database_path.parent / "privacy-status.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "not recorded"
    result = payload.get("result", "unknown") if isinstance(payload, dict) else "unknown"
    checked_at = payload.get("checked_at", "unknown") if isinstance(payload, dict) else "unknown"
    return f"{result} at {checked_at}"
