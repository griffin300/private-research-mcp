import asyncio
import contextlib
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.models import SearchMode
from app.orchestration.budgets import budget_for
from app.runtime import create_runtime
from app.storage.cache import Cache
from app.storage.database import Database
from app.storage.migrations import migrate
from app.storage.retention import clean_expired, run_retention_cleanup


def _insert_request(database: Database, request_id: str, created_at: str) -> None:
    database.execute(
        "INSERT INTO requests "
        "(request_id, query_hash, raw_query, created_at, duration_ms, source_count, "
        "evidence_count, coverage_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (request_id, "opaque-fingerprint", None, created_at, 1, 1, 1, 1.0),
    )


def test_strict_mode_rejects_same_proxy() -> None:
    with pytest.raises(ValueError, match="distinct"):
        Settings(search_proxy_url="socks5://tor:9050", fetch_proxy_url="socks5://tor:9050")


def test_cloud_planner_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="local or private"):
        Settings(
            allow_internal_llm_planner=True,
            lm_studio_planner_base_url="https://api.example.com/v1",
            lm_studio_planner_model="planner",
        )


def test_primary_model_endpoint_cannot_be_reused_for_planning() -> None:
    with pytest.raises(ValueError, match="separate"):
        Settings(
            allow_internal_llm_planner=True,
            lm_studio_planner_base_url="http://host.docker.internal:1234/v1",
            lm_studio_planner_model="planner",
        )


def test_search_budgets_are_configurable() -> None:
    settings = Settings(quick_pages=2, quick_queries=2, quick_browser_pages=1)
    budget = budget_for(SearchMode.QUICK, settings)
    assert (budget.queries, budget.pages, budget.browser_pages) == (2, 2, 1)


def test_interactive_limits_leave_model_generation_headroom() -> None:
    settings = Settings()

    assert settings.mcp_tool_deadline_seconds == 105
    assert settings.mcp_repeat_search_cooldown_seconds == 5
    assert (
        settings.quick_context_chars,
        settings.standard_context_chars,
        settings.deep_context_chars,
        settings.read_context_chars,
    ) == (8_000, 9_000, 10_000, 8_000)


def test_database_cache_round_trip(tmp_path) -> None:
    database = Database(tmp_path / "research.db")
    database.initialize()
    cache = Cache(database)
    key = cache.key({"q": "test", "mode": "quick"})
    cache.put("search", key, {"results": [1]}, timedelta(minutes=5))
    assert cache.get("search", key) == {"results": [1]}
    assert cache.stats() == {"hits": 1, "misses": 0, "hit_rate": 1.0}
    assert database.integrity()


def test_migration_adds_request_metrics_to_existing_database(tmp_path) -> None:
    database = Database(tmp_path / "old.db")
    database.initialize()
    database.execute("ALTER TABLE requests RENAME TO requests_new_schema")
    database.execute(
        "CREATE TABLE requests (request_id TEXT PRIMARY KEY, query_hash TEXT NOT NULL, "
        "raw_query TEXT, created_at TEXT NOT NULL, duration_ms INTEGER NOT NULL, "
        "source_count INTEGER NOT NULL, evidence_count INTEGER NOT NULL, coverage_score REAL NOT NULL)"
    )
    migrate(database)
    columns = {str(row[1]) for row in database.query_all("PRAGMA table_info(requests)")}
    assert {"queries_generated", "raw_results", "browser_fallbacks"} <= columns


def test_retention_removes_expired_evidence_index(tmp_path) -> None:
    database = Database(tmp_path / "retention.db")
    database.initialize()
    now = datetime.now(UTC)
    expired = (now - timedelta(days=1)).isoformat()
    fresh = (now + timedelta(days=1)).isoformat()
    old = (now - timedelta(days=8)).isoformat()
    _insert_request(database, "old-request", old)
    _insert_request(database, "fresh-request", now.isoformat())
    database.execute(
        "INSERT INTO cache_entries VALUES (?, ?, ?, ?, ?)",
        ("search", "old", "{}", old, fresh),
    )
    database.execute(
        "INSERT INTO cache_entries VALUES (?, ?, ?, ?, ?)",
        ("search", "fresh", "{}", now.isoformat(), fresh),
    )
    database.execute("INSERT INTO evidence_records VALUES (?, ?)", ("req:ev_001", expired))
    database.execute("INSERT INTO evidence_records VALUES (?, ?)", ("req:ev_002", fresh))
    database.execute(
        "INSERT INTO evidence_fts(evidence_id, source_id, heading, text) VALUES (?, ?, ?, ?)",
        ("req:ev_001", "src_001", "Heading", "Evidence"),
    )
    database.execute(
        "INSERT INTO evidence_fts(evidence_id, source_id, heading, text) VALUES (?, ?, ?, ?)",
        ("req:ev_002", "src_002", "Heading", "Fresh evidence"),
    )
    database.execute(
        "INSERT INTO evidence_fts(evidence_id, source_id, heading, text) VALUES (?, ?, ?, ?)",
        ("orphan", "src_003", "Heading", "Orphaned evidence"),
    )
    assert clean_expired(database, 7) == 1
    assert database.query_all("SELECT request_id FROM requests") == [("fresh-request",)]
    assert database.query_all("SELECT cache_key FROM cache_entries") == [("fresh",)]
    assert database.query_all("SELECT record_id FROM evidence_records") == [("req:ev_002",)]
    assert database.query_all("SELECT evidence_id FROM evidence_fts") == [("req:ev_002",)]


def test_retention_enables_secure_delete_and_truncates_wal(tmp_path) -> None:
    path = tmp_path / "physical-retention.db"
    database = Database(path)
    database.initialize()
    wal_path = path.with_name(f"{path.name}-wal")
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()

    # Keep one connection open so SQLite leaves the WAL file present and the
    # cleanup checkpoint can be observed directly.
    with contextlib.closing(sqlite3.connect(path)) as keeper:
        keeper.execute("PRAGMA journal_mode=WAL")
        _insert_request(database, "physical-old-request", old)
        assert database.query_one("PRAGMA secure_delete") == (1,)
        assert wal_path.exists() and wal_path.stat().st_size > 0

        clean_expired(database, 7)

        assert wal_path.exists() and wal_path.stat().st_size == 0


def test_zero_retention_purges_existing_data_and_blocks_query_derived_writes(tmp_path) -> None:
    path = tmp_path / "zero-retention.db"
    existing = Database(path)
    existing.initialize()
    _insert_request(existing, "existing", datetime.now(UTC).isoformat())
    existing.execute(
        "INSERT INTO cache_entries VALUES (?, ?, ?, ?, ?)",
        (
            "search",
            "existing",
            "{}",
            datetime.now(UTC).isoformat(),
            (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        ),
    )
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    existing.execute("INSERT INTO evidence_records VALUES (?, ?)", ("existing:ev_001", future))
    existing.execute(
        "INSERT INTO evidence_fts(evidence_id, source_id, heading, text) VALUES (?, ?, ?, ?)",
        ("existing:ev_001", "src_001", "Heading", "Previously retained evidence"),
    )

    runtime = create_runtime(
        Settings(
            privacy_mode="development",
            database_path=path,
            cache_retention_days=0,
        )
    )
    database = runtime.database
    _insert_request(database, "blocked", datetime.now(UTC).isoformat())
    Cache(database).put("search", "blocked", {"query": "sensitive"}, timedelta(days=1))
    database.execute_many(
        "INSERT OR REPLACE INTO evidence_records VALUES (?, ?)",
        [("blocked:ev_001", (datetime.now(UTC) + timedelta(days=1)).isoformat())],
    )
    database.execute_many(
        "INSERT INTO evidence_fts(evidence_id, source_id, heading, text) VALUES (?, ?, ?, ?)",
        [("blocked:ev_001", "src_001", "Heading", "Sensitive evidence")],
    )

    assert database.query_one("SELECT count(*) FROM requests")[0] == 0
    assert database.query_one("SELECT count(*) FROM cache_entries")[0] == 0
    assert database.query_one("SELECT count(*) FROM evidence_records")[0] == 0
    assert database.query_one("SELECT count(*) FROM evidence_fts")[0] == 0
    assert database.query_one("PRAGMA freelist_count") == (0,)
    assert b"Previously retained evidence" not in path.read_bytes()
    wal_path = path.with_name(f"{path.name}-wal")
    assert not wal_path.exists() or wal_path.stat().st_size == 0


@pytest.mark.asyncio
async def test_periodic_retention_cleans_rows_added_after_startup(tmp_path) -> None:
    database = Database(tmp_path / "periodic-retention.db")
    database.initialize()
    cleanup = asyncio.create_task(run_retention_cleanup(database, 7, interval_seconds=0.01))
    try:
        _insert_request(
            database,
            "added-after-startup",
            (datetime.now(UTC) - timedelta(days=8)).isoformat(),
        )
        for _ in range(50):
            if database.query_one("SELECT count(*) FROM requests")[0] == 0:
                break
            await asyncio.sleep(0.01)
        assert database.query_one("SELECT count(*) FROM requests")[0] == 0
    finally:
        cleanup.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup
