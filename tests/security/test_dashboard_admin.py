from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dashboard.routes import create_dashboard_router
from app.runtime import Runtime


class _RecordingDatabase:
    def __init__(self) -> None:
        self.clear_calls: list[list[str]] = []

    def clear(self, namespaces: list[str]) -> int:
        self.clear_calls.append(namespaces)
        return 7


def _client() -> tuple[TestClient, _RecordingDatabase]:
    database = _RecordingDatabase()
    runtime = cast(Runtime, cast(Any, type("StubRuntime", (), {"database": database})()))
    app = FastAPI()
    app.include_router(create_dashboard_router(runtime))
    return TestClient(app), database


def test_clear_accepts_confirmed_same_origin_loopback_post() -> None:
    client, database = _client()

    response = client.post(
        "/admin/clear?confirm=true",
        headers={
            "host": "127.0.0.1:8088",
            "origin": "http://127.0.0.1:8088",
            "sec-fetch-site": "same-origin",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"cleared": True, "rows": 7}
    assert len(database.clear_calls) == 1


def test_clear_rejects_cross_origin_form_post_without_deleting() -> None:
    client, database = _client()

    response = client.post(
        "/admin/clear?confirm=true",
        headers={
            "host": "127.0.0.1:8088",
            "origin": "https://attacker.example",
            "sec-fetch-site": "cross-site",
        },
    )

    assert response.status_code == 403
    assert database.clear_calls == []


def test_clear_rejects_requests_without_browser_origin_evidence() -> None:
    client, database = _client()

    response = client.post("/admin/clear?confirm=true", headers={"host": "127.0.0.1:8088"})

    assert response.status_code == 403
    assert database.clear_calls == []


def test_clear_rejects_dns_rebinding_host_even_with_matching_origin() -> None:
    client, database = _client()

    response = client.post(
        "/admin/clear?confirm=true",
        headers={"host": "attacker.example", "origin": "http://attacker.example"},
    )

    assert response.status_code == 403
    assert database.clear_calls == []


def test_clear_still_requires_explicit_confirmation() -> None:
    client, database = _client()

    response = client.post(
        "/admin/clear",
        headers={"host": "localhost:8088", "referer": "http://localhost:8088/dashboard"},
    )

    assert response.status_code == 400
    assert database.clear_calls == []


def test_clear_has_no_get_route() -> None:
    client, database = _client()

    response = client.get("/admin/clear?confirm=true")

    assert response.status_code == 405
    assert database.clear_calls == []
