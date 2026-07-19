from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.mcp_server import create_mcp_server
from app.models import CoverageReport, PrivacySummary, ResearchPackage
from app.runtime import create_runtime


@pytest.mark.security
async def test_mcp_tools_expose_compact_context_controls(tmp_path) -> None:
    runtime = create_runtime(
        Settings(
            privacy_mode="development",
            database_path=tmp_path / "mcp-schema.db",
        )
    )
    server = create_mcp_server(runtime)

    tools = {tool.name: tool for tool in await server.list_tools()}

    for name in ("search_web", "deep_research", "read_url"):
        properties = tools[name].inputSchema["properties"]
        assert properties["response_detail"]["default"] == "compact"
        budget_schema = properties["max_context_chars"]["anyOf"][0]
        assert budget_schema["minimum"] == 4_000
        assert budget_schema["maximum"] == 50_000


@pytest.mark.security
async def test_mcp_search_applies_interactive_return_deadline(tmp_path) -> None:
    runtime = create_runtime(
        Settings(
            privacy_mode="development",
            database_path=tmp_path / "mcp-deadline.db",
            mcp_tool_deadline_seconds=97,
        )
    )
    package = ResearchPackage(
        query="Define a cache.",
        mode="standard",
        request_id="deadline-test",
        search_rounds=1,
        coverage=CoverageReport(score=0, status="insufficient"),
        sources=[],
        evidence=[],
        privacy=PrivacySummary(
            search_transport="development",
            fetch_transport="development",
            direct_egress_allowed=False,
            mode="development",
        ),
    )
    search = AsyncMock(return_value=package)
    runtime.pipeline.search_web = search
    server = create_mcp_server(runtime)

    await server.call_tool("search_web", {"query": package.query, "mode": "standard"})
    _, repeated = await server.call_tool(
        "search_web", {"query": "Repeat immediately", "mode": "standard"}
    )

    assert search.await_args.kwargs["deadline_seconds_override"] == 97
    assert search.await_count == 1
    assert repeated["status"] == "repeated_search_suppressed"
    assert repeated["response_info"]["next_action"] == "answer_user_now"


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
