from __future__ import annotations

import ipaddress
import re
from urllib.parse import unquote, urlsplit


class UnsafeUrlError(ValueError):
    pass


_BLOCKED_HOSTS = {
    "localhost",
    "host.docker.internal",
    "gateway.docker.internal",
    "metadata.google.internal",
    "metadata.azure.internal",
    "instance-data",
    "searxng",
    "tor-search",
    "tor-fetch",
    "browser-service",
}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa")


def _parse_unusual_ipv4(host: str) -> ipaddress.IPv4Address | None:
    if re.fullmatch(r"\d+", host):
        value = int(host, 10)
        if 0 <= value <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(value)
    if re.fullmatch(r"0[xX][0-9a-fA-F]+", host):
        value = int(host, 16)
        if 0 <= value <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(value)
    parts = host.split(".")
    if len(parts) == 4 and all(re.fullmatch(r"0[0-7]+", part) for part in parts):
        return ipaddress.IPv4Address(bytes(int(part, 8) for part in parts))
    return None


def _is_forbidden_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def validate_url(url: str, *, allow_private: bool = False) -> str:
    if len(url) > 4096 or any(ord(char) < 32 for char in url):
        raise UnsafeUrlError("invalid URL encoding or length")
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeUrlError("only HTTP and HTTPS URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("embedded credentials are not allowed")
    host = unquote(parsed.hostname or "").rstrip(".").lower()
    if not host or "%" in host:
        raise UnsafeUrlError("URL has no valid host")
    if host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeUrlError("internal host is blocked")
    address: ipaddress.IPv4Address | ipaddress.IPv6Address | None = _parse_unusual_ipv4(host)
    if address is None:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
    if address is not None and not allow_private and _is_forbidden_address(address):
        raise UnsafeUrlError("private, local, or special-purpose address is blocked")
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise UnsafeUrlError("invalid port")
    return url
