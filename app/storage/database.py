from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS cache_entries (
  namespace TEXT NOT NULL,
  cache_key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  PRIMARY KEY(namespace, cache_key)
);
CREATE TABLE IF NOT EXISTS requests (
  request_id TEXT PRIMARY KEY,
  query_hash TEXT NOT NULL,
  raw_query TEXT,
  created_at TEXT NOT NULL,
  duration_ms INTEGER NOT NULL,
  source_count INTEGER NOT NULL,
  evidence_count INTEGER NOT NULL,
  coverage_score REAL NOT NULL,
  queries_generated INTEGER NOT NULL DEFAULT 0,
  raw_results INTEGER NOT NULL DEFAULT 0,
  pages_fetched INTEGER NOT NULL DEFAULT 0,
  extraction_failures INTEGER NOT NULL DEFAULT 0,
  browser_fallbacks INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS evidence_records (
  record_id TEXT PRIMARY KEY,
  expires_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
  evidence_id UNINDEXED, source_id UNINDEXED, heading, text
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(sql, parameters)
            connection.commit()

    def execute_many(self, sql: str, parameters: list[tuple[Any, ...]]) -> None:
        if not parameters:
            return
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executemany(sql, parameters)
            connection.commit()

    def query_one(self, sql: str, parameters: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(sql, parameters).fetchone()
            return tuple(row) if row is not None else None

    def query_all(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with closing(sqlite3.connect(self.path)) as connection:
            return [tuple(row) for row in connection.execute(sql, parameters).fetchall()]

    def stats(self) -> dict[str, int]:
        with closing(sqlite3.connect(self.path)) as connection:
            cache = int(connection.execute("SELECT count(*) FROM cache_entries").fetchone()[0])
            requests = int(connection.execute("SELECT count(*) FROM requests").fetchone()[0])
        return {"cache_entries": cache, "requests": requests, "bytes": self.path.stat().st_size}

    def recent_requests(self, limit: int = 10) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT request_id, created_at, duration_ms, queries_generated, raw_results, "
                "pages_fetched, extraction_failures, browser_fallbacks, source_count, "
                "evidence_count, coverage_score FROM requests ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        keys = (
            "request_id",
            "created_at",
            "duration_ms",
            "queries_generated",
            "raw_results",
            "pages_fetched",
            "extraction_failures",
            "browser_fallbacks",
            "source_count",
            "evidence_count",
            "coverage_score",
        )
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def integrity(self) -> bool:
        with closing(sqlite3.connect(self.path)) as connection:
            return str(connection.execute("PRAGMA quick_check").fetchone()[0]) == "ok"

    def clear(self, namespaces: list[str]) -> int:
        deleted = 0
        with closing(sqlite3.connect(self.path)) as connection:
            for namespace in namespaces:
                if namespace == "history":
                    deleted += connection.execute("DELETE FROM requests").rowcount
                elif namespace == "evidence":
                    deleted += connection.execute(
                        "DELETE FROM cache_entries WHERE namespace = ?", (namespace,)
                    ).rowcount
                    deleted += connection.execute("DELETE FROM evidence_fts").rowcount
                    deleted += connection.execute("DELETE FROM evidence_records").rowcount
                elif namespace in {"search", "pages", "extracted", "robots", "failures"}:
                    deleted += connection.execute(
                        "DELETE FROM cache_entries WHERE namespace = ?", (namespace,)
                    ).rowcount
            connection.commit()
        return deleted

    def clean_expired_evidence(self, cutoff: str) -> int:
        with closing(sqlite3.connect(self.path)) as connection:
            identifiers = [
                str(row[0])
                for row in connection.execute(
                    "SELECT record_id FROM evidence_records WHERE expires_at < ?", (cutoff,)
                ).fetchall()
            ]
            connection.executemany(
                "DELETE FROM evidence_fts WHERE evidence_id = ?",
                [(identifier,) for identifier in identifiers],
            )
            connection.executemany(
                "DELETE FROM evidence_records WHERE record_id = ?",
                [(identifier,) for identifier in identifiers],
            )
            connection.commit()
        return len(identifiers)

    @staticmethod
    def encode(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
