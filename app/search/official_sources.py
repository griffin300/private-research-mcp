from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.models import SearchResult

_MCP_REFERENCE_CUE = re.compile(
    r"\b(?:according\s+to|docs?|documentation|official|reference|manual|"
    r"how\s+to|which\s+transport|recommended\s+transport)\b",
    re.IGNORECASE,
)
_EXPLICIT_REFERENCE_CUE = re.compile(
    r"\b(?:according\s+to|docs?|documentation|official|reference|manual)\b",
    re.IGNORECASE,
)
_TROUBLESHOOTING_CUE = re.compile(
    r"\b(?:bug|broken|crash\w*|error|exception|fail\w*|not\s+working|timeout|"
    r"traceback|troubleshoot\w*)\b",
    re.IGNORECASE,
)
_SECURITY_ADVISORY_CUE = re.compile(
    r"\b(?:CVE-\d{4}-\d{4,7}|vulnerab\w*|exploit\w*|security\s+advisory|"
    r"affected\s+versions?|patched\s+versions?)\b",
    re.IGNORECASE,
)
_PYTHON_RELEASE_CUE = re.compile(
    r"\b(?:release(?:d|s)?|release\s+date|download|announcement|"
    r"became\s+available|availability)\b",
    re.IGNORECASE,
)
_REPOSITORY_COMPONENT = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})"
_PRICE_OR_COUNT_CONTEXT = {
    "amount",
    "cost",
    "costs",
    "count",
    "counts",
    "dollar",
    "dollars",
    "eur",
    "gbp",
    "pay",
    "price",
    "prices",
    "quantity",
    "total",
    "usd",
}


@dataclass(frozen=True, slots=True)
class OfficialSourceHint:
    url: str
    title: str


def official_source_candidates(query: str) -> list[SearchResult]:
    """Return bounded, deterministic primary-source candidates for recognized identifiers.

    These are local URL derivations, not network lookups. The normal fetch policy still
    retrieves every candidate through the isolated fetch Tor circuit.
    """
    hints = _official_source_hints(query)
    return [
        SearchResult(
            url=hint.url,
            title=hint.title,
            snippet="",
            engine="deterministic_official_source",
            engines=["deterministic_official_source"],
            search_score=1.0,
        )
        for hint in hints[:3]
    ]


def preferred_authority_domains(query: str) -> set[str]:
    """Infer authority preferences; preferences never exclude general web results."""
    normalized = query.casefold()
    domains = {urlsplit(hint.url).hostname or "" for hint in _official_source_hints(query)}
    if re.search(r"\b(?:rfc|http\s+status|internet standard|ietf)\b", normalized):
        domains.update({"iana.org", "rfc-editor.org", "ietf.org"})
    if re.search(r"\bpython\b", normalized):
        domains.update({"python.org", "docs.python.org", "peps.python.org"})
    if re.search(r"\bsqlite\b", normalized):
        domains.add("sqlite.org")
    if re.search(r"\bcurl\b", normalized):
        domains.update({"curl.se", "everything.curl.dev"})
    if re.search(r"\b(?:mcp|model context protocol)\b", normalized) and re.search(
        r"\b(?:docs?|documentation|official|protocol|reference|specification|transport)\b",
        normalized,
    ):
        domains.add("modelcontextprotocol.io")
    return {domain.casefold() for domain in domains if domain}


def domain_matches_authority(query: str, url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host == "raw.githubusercontent.com":
        return _mcp_python_sdk_document_path(query) is not None and parsed.path.casefold().startswith(
            "/modelcontextprotocol/python-sdk/"
        )
    if host in {"github.com", "www.github.com"}:
        repositories = _explicit_repositories(query)
        if _mcp_python_sdk_document_path(query) is not None:
            repositories.append("modelcontextprotocol/python-sdk")
        return any(_github_path_matches(parsed.path, repository) for repository in repositories)
    return any(
        host == domain or host.endswith(f".{domain}")
        for domain in preferred_authority_domains(query)
    )


def authority_search_variant(query: str) -> str | None:
    """Build one answer-independent primary-source query for the existing query budget."""
    normalized = query.casefold()
    mcp_path = _mcp_python_sdk_document_path(query)
    if mcp_path is not None:
        topic = (
            "server transport"
            if mcp_path == "/server/"
            else "client"
            if mcp_path == "/client/"
            else "installation"
            if mcp_path == "/installation/"
            else "documentation"
        )
        return f'site:py.sdk.modelcontextprotocol.io "MCP Python SDK" {topic}'
    python_version = re.search(r"\bpython\s+(\d+\.\d+(?:\.\d+)?)\b", query, re.I)
    if (
        python_version
        and _PYTHON_RELEASE_CUE.search(query)
        and not _SECURITY_ADVISORY_CUE.search(query)
    ):
        return f'site:python.org "Python {python_version.group(1)}" release'
    if re.search(r"\b(?:rfc|http\s+status|internet standard|ietf)\b", normalized):
        return f"site:rfc-editor.org {query}"
    if "sqlite" in normalized:
        return f"site:sqlite.org {query}"
    if "curl" in normalized:
        return f"site:curl.se {query}"
    return None


def distinctive_query_tokens(query: str) -> set[str]:
    """Extract identifiers whose absence is strong evidence that a result is off-topic."""
    tokens: set[str] = set()
    for value in re.findall(r"\bCVE-\d{4}-\d{4,7}\b", query, re.IGNORECASE):
        tokens.add(value.casefold())
    for value in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", query):
        tokens.add(value.casefold())
    for match in re.finditer(r"\b(?:version|ver\.?|v)\s*(\d+\.\d+(?:\.\d+){0,2})\b", query, re.I):
        tokens.add(match.group(1).casefold())
    for match in re.finditer(
        r"\b([A-Za-z][A-Za-z0-9+#.-]*)\s+(\d+\.\d+(?:\.\d+){0,2})\b",
        query,
    ):
        context, value = match.groups()
        if context.casefold() not in _PRICE_OR_COUNT_CONTEXT and (
            value.count(".") >= 2 or not _looks_currency_valued(query, match.start(2))
        ):
            tokens.add(value.casefold())
    typed_numbers = (
        r"\b(?:rfc|pep)\s*[-#:]?\s*(\d{1,5})\b",
        r"\bhttp\s+status(?:\s+code)?\s+(\d{3})\b",
        r"\b(?:status|error)\s+code\s*[:#-]?\s*(\d{3,5})\b",
        r"\b(?:port|issue)\s*[:#-]?\s*(\d{1,5})\b",
    )
    for pattern in typed_numbers:
        tokens.update(value.casefold() for value in re.findall(pattern, query, re.I))
    for value in re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", query):
        if value not in {"THE", "AND", "FOR"}:
            tokens.add(value.casefold())
    for value in _explicit_repositories(query):
        tokens.add(value.casefold())
    return tokens


def distinctive_anchor_coverage(query: str, text: str) -> float:
    anchors = distinctive_query_tokens(query)
    if not anchors:
        return 1.0
    normalized = text.casefold()
    matched = sum(
        bool(re.search(rf"(?<![a-z0-9]){re.escape(anchor)}(?![a-z0-9])", normalized))
        for anchor in anchors
    )
    return matched / len(anchors)


def _official_source_hints(query: str) -> list[OfficialSourceHint]:
    normalized = " ".join(query.casefold().split())
    hints: list[OfficialSourceHint] = []

    mcp_path = _mcp_python_sdk_document_path(query)
    if mcp_path is not None:
        hints.append(
            OfficialSourceHint(
                f"https://py.sdk.modelcontextprotocol.io{mcp_path}",
                "Official MCP Python SDK documentation",
            )
        )
        if mcp_path == "/server/":
            hints.append(
                OfficialSourceHint(
                    "https://raw.githubusercontent.com/modelcontextprotocol/"
                    "python-sdk/v1.x/docs/server.md",
                    "Official MCP Python SDK server transport documentation source",
                )
            )

    python_version = re.search(r"\bpython\s+(\d+)\.(\d+)\.(\d+)\b", normalized)
    if (
        python_version
        and _PYTHON_RELEASE_CUE.search(query)
        and not _SECURITY_ADVISORY_CUE.search(query)
    ):
        major, minor, patch = python_version.groups()
        slug = f"{major}{minor}{patch}"
        version = f"{major}.{minor}.{patch}"
        hints.append(
            OfficialSourceHint(
                f"https://www.python.org/downloads/release/python-{slug}/",
                f"Python {version} official release",
            )
        )

    http_status = re.search(r"\bhttp\s+status(?:\s+code)?\s+(\d{3})\b", normalized)
    if http_status:
        hints.append(
            OfficialSourceHint(
                "https://www.iana.org/assignments/http-status-codes/http-status-codes.xhtml",
                f"IANA official HTTP status code registry: {http_status.group(1)}",
            )
        )

    if (
        "ipv4" in normalized
        and "private" in normalized
        and re.search(r"\b(?:address|block|range)\w*\b", normalized)
    ):
        hints.append(
            OfficialSourceHint(
                "https://www.iana.org/assignments/iana-ipv4-special-registry/"
                "iana-ipv4-special-registry.xhtml",
                "IANA official IPv4 special-purpose address registry",
            )
        )

    for number in re.findall(r"\brfc\s*[-#:]?\s*(\d{3,5})\b", normalized)[:2]:
        hints.append(
            OfficialSourceHint(
                f"https://www.rfc-editor.org/rfc/rfc{number}.html",
                f"RFC {number} official publication",
            )
        )

    for number in re.findall(r"\bpep\s*[-#:]?\s*(\d{1,4})\b", normalized)[:2]:
        hints.append(
            OfficialSourceHint(
                f"https://peps.python.org/pep-{int(number):04d}/",
                f"PEP {int(number)} official publication",
            )
        )

    if "sqlite" in normalized and re.search(r"\b(?:wal|write[- ]ahead log)\b", normalized):
        hints.append(
            OfficialSourceHint(
                "https://www.sqlite.org/wal.html",
                "SQLite official write-ahead logging documentation",
            )
        )

    if "curl" in normalized and re.search(r"\bsocks5h?\b", normalized):
        hints.append(
            OfficialSourceHint(
                "https://curl.se/docs/manpage.html#--socks5-hostname",
                "curl official SOCKS proxy and hostname-resolution documentation",
            )
        )

    for repository in _explicit_repositories(query)[:2]:
        hints.append(
            OfficialSourceHint(
                f"https://github.com/{repository}",
                f"Official source repository {repository}",
            )
        )

    unique: list[OfficialSourceHint] = []
    seen: set[str] = set()
    for hint in hints:
        if hint.url not in seen:
            seen.add(hint.url)
            unique.append(hint)
    return unique


def _mcp_python_sdk_document_path(query: str) -> str | None:
    normalized = " ".join(query.casefold().split())
    if not (
        re.search(r"\b(?:mcp|model context protocol)\b", normalized)
        and "python" in normalized
        and "sdk" in normalized
        and _MCP_REFERENCE_CUE.search(query)
        and not _SECURITY_ADVISORY_CUE.search(query)
    ):
        return None
    if _TROUBLESHOOTING_CUE.search(query) and not _EXPLICIT_REFERENCE_CUE.search(query):
        return None
    if re.search(r"\b(?:server|deploy|deployment|transport|streamable|stdio|sse)\b", normalized):
        return "/server/"
    if re.search(r"\b(?:client|connect|connection|oauth|authorization)\b", normalized):
        return "/client/"
    if re.search(r"\b(?:install|installation|pip|uv)\b", normalized):
        return "/installation/"
    return "/"


def _explicit_repositories(query: str) -> list[str]:
    if not re.search(r"\b(?:github|repo|repository|source\s+code)\b", query, re.I):
        return []
    github_url_pattern = (
        rf"(?:https?://)?(?:www\.)?github\.com/"
        rf"({_REPOSITORY_COMPONENT}/{_REPOSITORY_COMPONENT})(?:/[^\s]*)?"
    )
    repositories = re.findall(
        github_url_pattern,
        query,
        re.IGNORECASE,
    )
    without_github_urls = re.sub(github_url_pattern, " ", query, flags=re.IGNORECASE)
    repositories.extend(
        re.findall(
            rf"(?<![\w.-])({_REPOSITORY_COMPONENT}/{_REPOSITORY_COMPONENT})(?![\w.-])",
            without_github_urls,
        )
    )
    unique: list[str] = []
    seen: set[str] = set()
    for repository in repositories:
        lowered = repository.casefold()
        if lowered.startswith(("http/", "https/", "github.com/")) or lowered in seen:
            continue
        seen.add(lowered)
        unique.append(repository)
    return unique


def _github_path_matches(path: str, repository: str) -> bool:
    normalized_path = "/" + path.casefold().strip("/")
    required = "/" + repository.casefold().strip("/")
    return normalized_path == required or normalized_path.startswith(f"{required}/")


def _looks_currency_valued(query: str, value_start: int) -> bool:
    prefix = query[max(0, value_start - 5) : value_start]
    return bool(re.search(r"(?:[$\u00a3\u20ac]|USD|EUR|GBP)\s*$", prefix, re.I))


__all__ = [
    "authority_search_variant",
    "distinctive_anchor_coverage",
    "distinctive_query_tokens",
    "domain_matches_authority",
    "official_source_candidates",
    "preferred_authority_domains",
]
