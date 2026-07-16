from __future__ import annotations

import re
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_KEYS = re.compile(
    r"(?:^|[_\-.])(?:api[_-]?key|token|secret|password|key|auth|authorization|signature|sig|"
    r"credential|access[_-]?id|session(?:[_-]?id)?|jwt|bearer|code)(?=$|[_\-.])",
    re.I,
)
_FINGERPRINT_KEY = secrets.token_bytes(32)


def _is_sensitive_key(key: str) -> bool:
    # Normalize camelCase and vendor separators so apiKey, X-Amz-Credential,
    # access-id, OAuth code, Azure SAS sig, and sessionId are treated alike.
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key).replace("-", "_")
    return bool(SECRET_KEYS.search(normalized))


def has_sensitive_query(url: str) -> bool:
    parsed = urlsplit(url)
    parameters = [
        *parse_qsl(parsed.query, keep_blank_values=True),
        *parse_qsl(parsed.fragment, keep_blank_values=True),
    ]
    return any(_is_sensitive_key(key) for key, _ in parameters)


def redact_url(url: str) -> str:
    parsed = urlsplit(url)
    query = [
        (key, "[REDACTED]" if _is_sensitive_key(key) else value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def query_fingerprint(query: str) -> str:
    import hashlib
    import hmac

    return hmac.new(_FINGERPRINT_KEY, query.encode(), hashlib.sha256).hexdigest()[:16]
