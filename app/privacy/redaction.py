from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_KEYS = re.compile(r"(token|secret|password|key|auth|signature)", re.I)


def redact_url(url: str) -> str:
    parsed = urlsplit(url)
    query = [
        (key, "[REDACTED]" if SECRET_KEYS.search(key) else value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def query_fingerprint(query: str) -> str:
    import hashlib

    return hashlib.sha256(query.encode()).hexdigest()[:16]
