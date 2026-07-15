from pathlib import Path

import pytest


@pytest.mark.privacy
def test_compose_contains_network_privacy_boundary() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "internal: true" in compose
    assert "127.0.0.1:8088:8088" in compose
    assert 'enable_ip_masquerade: "false"' in compose
    assert "tor-search" in compose and "tor-fetch" in compose
    app_block = compose.split("  app:", 1)[1].split("\n  mcp-bridge:", 1)[0]
    assert "egress_search" not in app_block and "egress_fetch" not in app_block
    assert "ports:" not in app_block


@pytest.mark.privacy
def test_no_cloud_api_domains_in_runtime_configuration() -> None:
    content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [Path(".env.example"), Path("docker-compose.yml")]
    )
    for domain in ("api.openai.com", "api.anthropic.com", "api.tavily.com", "api.exa.ai"):
        assert domain not in content
