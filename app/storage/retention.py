from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.storage.database import Database

logger = logging.getLogger(__name__)
RETENTION_CLEANUP_INTERVAL_SECONDS = 300.0


def clean_expired(database: Database, retention_days: int) -> int:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=retention_days)
    return database.clean_retained_query_data(
        now=now.isoformat(),
        request_cutoff=cutoff.isoformat(),
        purge_all=retention_days == 0,
    )


async def run_retention_cleanup(
    database: Database,
    retention_days: int,
    *,
    interval_seconds: float = RETENTION_CLEANUP_INTERVAL_SECONDS,
) -> None:
    """Continuously enforce retention for a long-running MCP process."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(clean_expired, database, retention_days)
        except Exception:  # pragma: no cover - defensive; the next sweep must still run.
            logger.exception("Periodic retention cleanup failed")
