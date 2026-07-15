from __future__ import annotations

from dataclasses import dataclass

ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/json",
    "application/ld+json",
}


@dataclass(frozen=True, slots=True)
class FetchPolicy:
    max_response_bytes: int
    max_redirects: int
    timeout_seconds: float
    retries: int = 1
    user_agent: str = "PrivateResearchMCP/0.1 (+local evidence retrieval)"
