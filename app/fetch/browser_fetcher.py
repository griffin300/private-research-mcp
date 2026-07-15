from __future__ import annotations

from datetime import datetime

import httpx

from app.fetch.url_safety import validate_url
from app.models import FetchResult


class BrowserFetcher:
    def __init__(self, service_url: str, timeout: float, enabled: bool) -> None:
        self.service_url = service_url.rstrip("/")
        self.timeout = timeout
        self.enabled = enabled

    async def fetch(self, url: str) -> FetchResult:
        if not self.enabled:
            raise RuntimeError("browser fallback disabled")
        validate_url(url)
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(f"{self.service_url}/render", json={"url": url})
            response.raise_for_status()
            data = response.json()
        return FetchResult(
            requested_url=url,
            final_url=str(data["final_url"]),
            status_code=int(data["status_code"]),
            content_type="text/html",
            body=str(data["html"]),
            method="browser",
            retrieved_at=datetime.fromisoformat(str(data["retrieved_at"])),
        )

    async def health(self) -> dict[str, object]:
        if not self.enabled:
            return {"status": "disabled"}
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 5), trust_env=False) as client:
                response = await client.get(f"{self.service_url}/health")
            return {
                "status": "healthy" if response.is_success else "unhealthy",
                "code": response.status_code,
            }
        except httpx.HTTPError as exc:
            return {"status": "unhealthy", "error": type(exc).__name__}
