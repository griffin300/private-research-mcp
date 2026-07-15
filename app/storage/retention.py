from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.storage.database import Database


def clean_expired(database: Database, retention_days: int) -> int:
    cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
    before = database.query_one("SELECT count(*) FROM cache_entries")
    database.clean_expired_evidence(datetime.now(UTC).isoformat())
    database.execute(
        "DELETE FROM cache_entries WHERE expires_at < ? OR created_at < ?",
        (datetime.now(UTC).isoformat(), cutoff),
    )
    after = database.query_one("SELECT count(*) FROM cache_entries")
    return int(before[0]) - int(after[0]) if before and after else 0
