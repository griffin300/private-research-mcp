from __future__ import annotations

from app.config import Settings


def configuration_network_check(settings: Settings) -> dict[str, object]:
    separated = bool(
        settings.search_proxy_url
        and settings.fetch_proxy_url
        and settings.search_proxy_url != settings.fetch_proxy_url
    )
    return {
        "strict": settings.privacy_mode == "strict",
        "separate_transports": separated,
        "direct_egress_allowed": settings.direct_egress_allowed,
        "pass": separated and not settings.direct_egress_allowed
        if settings.privacy_mode == "strict"
        else True,
    }
