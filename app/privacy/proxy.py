from __future__ import annotations


def proxy_health_label(configured_url: str, required: bool) -> dict[str, object]:
    return {
        "status": "configured" if configured_url else "unhealthy" if required else "disabled",
        "required": required,
    }
