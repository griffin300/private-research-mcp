from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

from app.storage.database import Database
from app.storage.retention import (
    RETENTION_CLEANUP_INTERVAL_SECONDS,
    run_retention_cleanup,
)


@contextlib.asynccontextmanager
async def managed_http_lifespan(
    mcp_server: Any,
    database: Database,
    retention_days: int,
    *,
    cleanup_interval_seconds: float = RETENTION_CLEANUP_INTERVAL_SECONDS,
) -> AsyncIterator[None]:
    """Keep HTTP session management and retention alive for the ASGI process lifetime."""
    cleanup = asyncio.create_task(
        run_retention_cleanup(
            database,
            retention_days,
            interval_seconds=cleanup_interval_seconds,
        ),
        name="retention-cleanup-http",
    )
    try:
        async with mcp_server.session_manager.run():
            yield
    finally:
        cleanup.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup
