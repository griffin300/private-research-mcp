from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

_QUERY_DATA_INSERT = re.compile(
    r"^\s*(?:insert(?:\s+or\s+\w+)?|replace)\s+into\s+"
    r"(?:main\.)?(?:cache_entries|requests|evidence_records|evidence_fts)\b",
    re.IGNORECASE,
)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA secure_delete=ON;
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
        self._query_data_persistence = True

    def set_query_data_persistence(self, enabled: bool) -> None:
        """Enable or disable writes to query-derived storage tables.

        Migrations run with persistence enabled. Runtime configuration applies this
        gate immediately afterwards, so a zero-day retention policy cannot create
        request fingerprints, evidence/FTS rows, or cache entries.
        """
        self._query_data_persistence = enabled

    def _write_is_permitted(self, sql: str) -> bool:
        return self._query_data_persistence or _QUERY_DATA_INSERT.match(sql) is None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys=ON")
        # This setting is connection-local, so apply it to every short-lived
        # connection instead of relying only on the initialization script.
        connection.execute("PRAGMA secure_delete=ON")
        return connection

    @staticmethod
    def _truncate_wal(connection: sqlite3.Connection) -> None:
        # SQLite reports a busy reader in the first result column rather than
        # raising. A later retention sweep retries the checkpoint in that case.
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        if not self._write_is_permitted(sql):
            return
        with closing(self._connect()) as connection:
            connection.execute(sql, parameters)
            connection.commit()

    def execute_many(self, sql: str, parameters: list[tuple[Any, ...]]) -> None:
        if not parameters or not self._write_is_permitted(sql):
            return
        with closing(self._connect()) as connection:
            connection.executemany(sql, parameters)
            connection.commit()

    def query_one(self, sql: str, parameters: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(sql, parameters).fetchone()
            return tuple(row) if row is not None else None

    def query_all(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with closing(self._connect()) as connection:
            return [tuple(row) for row in connection.execute(sql, parameters).fetchall()]

    def stats(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            cache = int(connection.execute("SELECT count(*) FROM cache_entries").fetchone()[0])
            requests = int(connection.execute("SELECT count(*) FROM requests").fetchone()[0])
        return {"cache_entries": cache, "requests": requests, "bytes": self.path.stat().st_size}

    def recent_requests(self, limit: int = 10) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
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
        with closing(self._connect()) as connection:
            return str(connection.execute("PRAGMA quick_check").fetchone()[0]) == "ok"

    def clear(self, namespaces: list[str]) -> int:
        deleted = 0
        with closing(self._connect()) as connection:
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
            self._truncate_wal(connection)
        return deleted

    def clean_expired_evidence(self, cutoff: str) -> int:
        with closing(self._connect()) as connection:
            identifiers = [
                str(row[0])
                for row in connection.execute(
                    "SELECT record_id FROM evidence_records WHERE expires_at <= ?", (cutoff,)
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
            connection.execute(
                "DELETE FROM evidence_fts WHERE evidence_id NOT IN "
                "(SELECT record_id FROM evidence_records)"
            )
            connection.commit()
            self._truncate_wal(connection)
        return len(identifiers)

    def clean_retained_query_data(
        self, *, now: str, request_cutoff: str, purge_all: bool = False
    ) -> int:
        """Atomically purge expired caches/evidence and aged request metadata.

        The return value preserves ``clean_expired``'s historical contract: it is
        the number of removed cache rows. Request/evidence deletion is deliberately
        included in the same transaction but not in that count.
        """
        with closing(self._connect()) as connection:
            if purge_all:
                cache_deleted = connection.execute("DELETE FROM cache_entries").rowcount
                evidence_fts_deleted = connection.execute("DELETE FROM evidence_fts").rowcount
                evidence_deleted = connection.execute("DELETE FROM evidence_records").rowcount
                requests_deleted = connection.execute("DELETE FROM requests").rowcount
                connection.commit()
                self._truncate_wal(connection)
                deleted_rows = sum(
                    max(0, count)
                    for count in (
                        cache_deleted,
                        evidence_fts_deleted,
                        evidence_deleted,
                        requests_deleted,
                    )
                )
                freelist_count = int(
                    connection.execute("PRAGMA freelist_count").fetchone()[0]
                )
                if deleted_rows or freelist_count:
                    # secure_delete overwrites deleted cells, while VACUUM rewrites
                    # the database to remove freed pages (including FTS shadow data).
                    # Skip repeated VACUUM work once a zero-retention database is empty.
                    connection.execute("VACUUM")
                    self._truncate_wal(connection)
                return max(0, cache_deleted)
            identifiers = [
                str(row[0])
                for row in connection.execute(
                    "SELECT record_id FROM evidence_records WHERE expires_at <= ?", (now,)
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
            connection.execute(
                "DELETE FROM evidence_fts WHERE evidence_id NOT IN "
                "(SELECT record_id FROM evidence_records)"
            )
            cache_deleted = connection.execute(
                "DELETE FROM cache_entries WHERE expires_at <= ? OR created_at <= ?",
                (now, request_cutoff),
            ).rowcount
            connection.execute("DELETE FROM requests WHERE created_at <= ?", (request_cutoff,))
            connection.commit()
            self._truncate_wal(connection)
        return max(0, cache_deleted)

    @staticmethod
    def encode(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
