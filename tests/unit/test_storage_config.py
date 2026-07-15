from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.models import SearchMode
from app.orchestration.budgets import budget_for
from app.storage.cache import Cache
from app.storage.database import Database
from app.storage.migrations import migrate
from app.storage.retention import clean_expired


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
    expired = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    database.execute("INSERT INTO evidence_records VALUES (?, ?)", ("req:ev_001", expired))
    database.execute(
        "INSERT INTO evidence_fts(evidence_id, source_id, heading, text) VALUES (?, ?, ?, ?)",
        ("req:ev_001", "src_001", "Heading", "Evidence"),
    )
    clean_expired(database, 7)
    assert database.query_one("SELECT count(*) FROM evidence_records")[0] == 0
    assert database.query_one("SELECT count(*) FROM evidence_fts")[0] == 0
