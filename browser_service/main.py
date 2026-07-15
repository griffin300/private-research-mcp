from __future__ import annotations

import os
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from playwright.async_api import Route, async_playwright
from pydantic import BaseModel

from app.fetch.url_safety import UnsafeUrlError, validate_url

app = FastAPI(title="private-research-browser", docs_url=None, redoc_url=None)
BLOCKED_TYPES = {"image", "media", "font", "websocket", "eventsource"}
BLOCKED_HOST_PARTS = ("google-analytics", "doubleclick", "segment.io", "hotjar", "facebook.net")


class RenderRequest(BaseModel):
    url: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/render")
async def render(request: RenderRequest) -> dict[str, object]:
    try:
        validate_url(request.url)
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    proxy = os.environ.get("BROWSER_PROXY_URL")
    if not proxy:
        raise HTTPException(status_code=503, detail="privacy proxy unavailable")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            proxy={"server": proxy},
            args=["--disable-webrtc", "--disable-features=WebRtcHideLocalIpsWithMdns"],
        )
        context = await browser.new_context(
            java_script_enabled=True,
            service_workers="block",
            accept_downloads=False,
            permissions=[],
            locale="en-US",
            timezone_id="UTC",
            geolocation=None,
            extra_http_headers={"DNT": "1", "Referer": ""},
        )

        async def filter_route(route: Route) -> None:
            host = (urlsplit(route.request.url).hostname or "").lower()
            if route.request.resource_type in BLOCKED_TYPES or any(
                part in host for part in BLOCKED_HOST_PARTS
            ):
                await route.abort()
            else:
                try:
                    validate_url(route.request.url)
                except UnsafeUrlError:
                    await route.abort()
                else:
                    await route.continue_()

        await context.route("**/*", filter_route)
        page = await context.new_page()
        response = await page.goto(request.url, wait_until="domcontentloaded", timeout=20_000)
        await page.wait_for_timeout(1000)
        final_url = page.url
        validate_url(final_url)
        html = await page.content()
        status = response.status if response else 200
        await context.close()
        await browser.close()
    return {
        "final_url": final_url,
        "status_code": status,
        "html": html,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
