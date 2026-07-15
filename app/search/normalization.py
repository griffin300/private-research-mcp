from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models import SearchResult

TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "ref_src",
    "igshid",
}
TRACKING_PREFIXES = ("utm_", "pk_", "vero_", "ga_")


def normalize_url(url: str) -> str:
    value = url.strip()
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").rstrip(".").lower()
    port = parsed.port
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if not port or default_port else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_KEYS and not key.lower().startswith(TRACKING_PREFIXES)
    ]
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


def normalize_result(result: SearchResult) -> SearchResult:
    normalized = normalize_url(result.url)
    domain = urlsplit(normalized).hostname or ""
    result.url = normalized
    result.canonical_url = (
        normalize_url(result.canonical_url) if result.canonical_url else normalized
    )
    result.domain = domain
    result.title = " ".join(result.title.split())
    result.snippet = " ".join(result.snippet.split())
    result.engines = sorted(set(result.engines or [result.engine]))
    return result
