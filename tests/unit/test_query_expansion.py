import httpx
import pytest
import respx

from app.orchestration.planner import EnhancedQueryPlanner
from app.search.query_expansion import HeuristicQueryPlanner


def test_query_expansion_is_deterministic_and_bounded() -> None:
    planner = HeuristicQueryPlanner()
    first = planner.plan("Latest MCP release vs older versions", 6)
    second = planner.plan("Latest MCP release vs older versions", 6)
    assert first == second
    assert len(first.queries) <= 6
    assert first.time_sensitive
    assert any("official documentation" in query for query in first.queries)


def test_error_message_adds_exact_phrase_query() -> None:
    plan = HeuristicQueryPlanner().plan("Python error connection failed", 8)
    assert any("issue tracker" in query and '"' in query for query in plan.queries)


def test_historical_release_does_not_get_current_release_notes() -> None:
    plan = HeuristicQueryPlanner().plan("On what date was Python 3.12.0 released?", 6)
    assert not plan.time_sensitive
    assert not any("current release notes" in query for query in plan.queries)
    assert any("Python 3.12.0 released" in query for query in plan.queries)


@pytest.mark.asyncio
@respx.mock
async def test_enhanced_planner_uses_only_configured_local_endpoint() -> None:
    fallback = HeuristicQueryPlanner().plan("Compare MCP transports", 4)
    respx.post("http://planner:1234/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"queries":["MCP transport specification"],"topics":["MCP transports"],"time_sensitive":false}'
                        }
                    }
                ]
            },
        )
    )
    plan = await EnhancedQueryPlanner("http://planner:1234/v1", "local-planner", 2).plan(
        "Compare MCP transports", fallback, 4
    )
    assert plan.queries[0] == "MCP transport specification"
    assert len(plan.queries) <= 4
