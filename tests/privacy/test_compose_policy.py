import re
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
    searxng_block = compose.split("  searxng:", 1)[1].split("\n  browser-service:", 1)[0]
    assert "egress_search" not in app_block and "egress_fetch" not in app_block
    assert "ports:" not in app_block
    assert 'driver: "none"' in searxng_block


@pytest.mark.privacy
def test_no_cloud_api_domains_in_runtime_configuration() -> None:
    content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [Path(".env.example"), Path("docker-compose.yml")]
    )
    for domain in ("api.openai.com", "api.anthropic.com", "api.tavily.com", "api.exa.ai"):
        assert domain not in content


@pytest.mark.privacy
def test_searxng_uses_bounded_tor_circuit_isolation_pool() -> None:
    settings = Path("config/searxng/settings.yml").read_text(encoding="utf-8")
    labels = re.findall(r"socks5h://([^:]+):([^@]+)@tor-search:9050", settings)
    assert len(labels) == 4
    assert len(set(labels)) == 4
    assert len({username for username, _ in labels}) == 4
    assert len({password for _, password in labels}) == 4
    assert "retries: 0" in settings
    assert "using_tor_proxy: true" in settings
    torrc = Path("config/tor-search/torrc").read_text(encoding="utf-8")
    assert "IsolateSOCKSAuth" in torrc


@pytest.mark.privacy
def test_bridge_recovers_without_widening_egress() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    bridge_block = compose.split("  mcp-bridge:", 1)[1].split("\nnetworks:", 1)[0]
    entrypoint = Path("mcp_bridge/entrypoint.sh").read_text(encoding="utf-8")
    connector = Path("mcp_bridge/connect-app.sh").read_text(encoding="utf-8")

    assert "condition: service_healthy\n        restart: true" in bridge_block
    assert '127.0.0.1:8088:8088' in bridge_block
    assert "egress_search" not in bridge_block and "egress_fetch" not in bridge_block
    assert "iptables -P OUTPUT DROP" in entrypoint
    assert "--uid-owner 0" in entrypoint
    assert '-o lo -p tcp --dport "$APP_PORT"' in entrypoint
    assert 'direct_route_device "$candidate"' in entrypoint
    assert '"$candidate_device" = "$APP_DEVICE"' in entrypoint
    assert 'getent hosts "$APP_HOST"' in entrypoint
    assert 'iptables -A "$APP_CHAIN" -d "$new_ip"/32' in entrypoint
    assert "TCP4-LISTEN:" in entrypoint
    assert "cat /tmp/app_ip" in connector
    assert 'TCP4:"$APP_IP":8088' in connector
