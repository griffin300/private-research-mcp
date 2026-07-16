from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.storage.database import Database


class Cache:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(value: dict[str, Any]) -> str:
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def get(self, namespace: str, key: str) -> Any | None:
        row = self.database.query_one(
            "SELECT value_json, expires_at FROM cache_entries WHERE namespace=? AND cache_key=?",
            (namespace, key),
        )
        if not row or datetime.fromisoformat(str(row[1])) <= datetime.now(UTC):
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(str(row[0]))

    def stats(self) -> dict[str, int | float]:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }

    def put(self, namespace: str, key: str, value: Any, ttl: timedelta) -> None:
        now = datetime.now(UTC)
        self.database.execute(
            "INSERT OR REPLACE INTO cache_entries VALUES (?, ?, ?, ?, ?)",
            (namespace, key, self.database.encode(value), now.isoformat(), (now + ttl).isoformat()),
        )

    def delete(self, namespace: str, key: str) -> None:
        self.database.execute(
            "DELETE FROM cache_entries WHERE namespace=? AND cache_key=?", (namespace, key)
        )
