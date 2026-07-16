from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from app.fetch.policies import ALLOWED_CONTENT_TYPES, FetchPolicy
from app.fetch.url_safety import validate_url
from app.models import FetchResult


class FetchError(RuntimeError):
    pass


class HttpFetcher:
    def __init__(
        self,
        *,
        policy: FetchPolicy,
        proxy_url: str | None,
        strict_privacy: bool,
        allow_private: bool = False,
        per_domain_concurrency: int = 2,
    ) -> None:
        if strict_privacy and not proxy_url:
            raise ValueError("strict privacy mode requires a fetch proxy")
        self.policy = policy
        self.proxy_url = proxy_url
        self.strict_privacy = strict_privacy
        self.allow_private = allow_private
        self.per_domain_concurrency = per_domain_concurrency
        self._domain_limits: dict[str, asyncio.Semaphore] = {}
        self._circuit_failures: dict[str, int] = {}
        self._circuit_open_until: dict[str, float] = {}

    async def fetch(self, url: str) -> FetchResult:
        validate_url(url, allow_private=self.allow_private)
        domain = (urlsplit(url).hostname or "").lower()
        if self._circuit_open_until.get(domain, 0) > time.monotonic():
            raise FetchError("domain circuit breaker is open")
        last_error: Exception | None = None
        semaphore = self._domain_limits.setdefault(
            domain, asyncio.Semaphore(self.per_domain_concurrency)
        )
        async with semaphore:
            if self._circuit_open_until.get(domain, 0) > time.monotonic():
                raise FetchError("domain circuit breaker is open")
            total_timeout = self.policy.timeout_seconds * (self.policy.retries + 1)
            try:
                async with asyncio.timeout(total_timeout):
                    async with self._client() as client:
                        for attempt in range(self.policy.retries + 1):
                            try:
                                result = await self._fetch_once(client, url)
                                self._circuit_failures.pop(domain, None)
                                self._circuit_open_until.pop(domain, None)
                                return result
                            except (httpx.HTTPError, FetchError) as exc:
                                last_error = exc
                                if attempt >= self.policy.retries or not _is_transient(exc):
                                    break
                                await asyncio.sleep(
                                    0.15 * (2**attempt) + random.random() * 0.1  # noqa: S311
                                )
            except TimeoutError as exc:
                last_error = exc
        if last_error is not None and _is_transient(last_error):
            failures = self._circuit_failures.get(domain, 0) + 1
            self._circuit_failures[domain] = failures
            if failures >= 3:
                self._circuit_open_until[domain] = time.monotonic() + 60
        else:
            self._circuit_failures.pop(domain, None)
            self._circuit_open_until.pop(domain, None)
        raise FetchError(
            f"fetch failed without direct fallback: {type(last_error).__name__}"
        ) from last_error

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            proxy=self.proxy_url,
            timeout=httpx.Timeout(self.policy.timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": self.policy.user_agent, "Accept": "text/html,text/plain;q=0.8"},
        )

    async def _fetch_once(self, client: httpx.AsyncClient, url: str) -> FetchResult:
        current = url
        for redirect_number in range(self.policy.max_redirects + 1):
            validate_url(current, allow_private=self.allow_private)
            async with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError("redirect had no destination")
                    if redirect_number >= self.policy.max_redirects:
                        raise FetchError("maximum redirects exceeded")
                    current = urljoin(current, location)
                    validate_url(current, allow_private=self.allow_private)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type not in ALLOWED_CONTENT_TYPES:
                    raise FetchError(f"unsupported content type: {content_type or 'missing'}")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self.policy.max_response_bytes:
                        raise FetchError("response exceeds configured size limit")
                    chunks.append(chunk)
                body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                return FetchResult(
                    requested_url=url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=content_type,
                    body=body,
                    headers={
                        key.lower(): value
                        for key, value in response.headers.items()
                        if key.lower() in {"last-modified", "etag", "content-language"}
                    },
                    retrieved_at=datetime.now(UTC),
                )
        raise FetchError("redirect processing failed")


def _is_transient(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in {408, 425, 429, 500, 502, 503, 504}
    return isinstance(error, TimeoutError | httpx.RequestError)
