from __future__ import annotations

from app.config import Settings
from app.privacy.network_checks import configuration_network_check


def audit_configuration(settings: Settings) -> list[str]:
    warnings: list[str] = []
    check = configuration_network_check(settings)
    if not check["pass"]:
        warnings.append("network configuration does not satisfy strict privacy policy")
    if settings.log_raw_queries:
        warnings.append("raw query logging is enabled")
    if settings.store_search_history:
        warnings.append("search history persistence is enabled")
    if settings.admin_host != "127.0.0.1" or settings.mcp_host != "127.0.0.1":
        warnings.append("a local service is not bound to loopback")
    return warnings
