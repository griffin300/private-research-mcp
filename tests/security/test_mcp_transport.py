import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.mcp_server import create_mcp_server
from app.runtime import create_runtime


@pytest.mark.security
def test_internal_bridge_host_header_is_rejected_by_mcp_transport(tmp_path) -> None:
    runtime = create_runtime(
        Settings(
            privacy_mode="development",
            database_path=tmp_path / "mcp-host-security.db",
        )
    )
    server = create_mcp_server(runtime)

    with TestClient(server.streamable_http_app(), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/",
            headers={"host": "mcp-bridge:8088", "content-type": "application/json"},
            json={},
        )

    assert response.status_code == 421
