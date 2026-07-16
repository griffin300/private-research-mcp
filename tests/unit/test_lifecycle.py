import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from app.lifecycle import managed_http_lifespan
from app.storage.database import Database


class _SessionManager:
    def __init__(self) -> None:
        self.active = False

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        self.active = True
        try:
            yield
        finally:
            self.active = False


class _McpServer:
    def __init__(self) -> None:
        self.session_manager = _SessionManager()


async def test_http_lifespan_keeps_periodic_retention_alive(tmp_path) -> None:
    database = Database(tmp_path / "http-lifespan.db")
    database.initialize()
    server = _McpServer()
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()

    async with managed_http_lifespan(
        server,
        database,
        7,
        cleanup_interval_seconds=0.01,
    ):
        database.execute(
            "INSERT INTO requests "
            "(request_id, query_hash, raw_query, created_at, duration_ms, source_count, "
            "evidence_count, coverage_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("aged", "opaque", None, old, 1, 0, 0, 0.0),
        )
        for _ in range(50):
            if database.query_one("SELECT count(*) FROM requests") == (0,):
                break
            await asyncio.sleep(0.01)
        assert server.session_manager.active
        assert database.query_one("SELECT count(*) FROM requests") == (0,)

    assert not server.session_manager.active
