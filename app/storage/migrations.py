from __future__ import annotations

from app.storage.database import Database


def migrate(database: Database) -> None:
    database.initialize()
    columns = {str(row[1]) for row in database.query_all("PRAGMA table_info(requests)")}
    request_columns = {
        "queries_generated": "INTEGER NOT NULL DEFAULT 0",
        "raw_results": "INTEGER NOT NULL DEFAULT 0",
        "pages_fetched": "INTEGER NOT NULL DEFAULT 0",
        "extraction_failures": "INTEGER NOT NULL DEFAULT 0",
        "browser_fallbacks": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, declaration in request_columns.items():
        if name not in columns:
            database.execute(f"ALTER TABLE requests ADD COLUMN {name} {declaration}")
    schema = database.query_one(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence_records'"
    )
    if schema and "evidence_id" in str(schema[0]) and "record_id" not in str(schema[0]):
        database.execute("ALTER TABLE evidence_records RENAME TO evidence_records_legacy")
        database.execute(
            "CREATE TABLE evidence_records (record_id TEXT PRIMARY KEY, expires_at TEXT NOT NULL)"
        )
        database.execute(
            "INSERT INTO evidence_records(record_id, expires_at) "
            "SELECT request_id || ':' || evidence_id, expires_at FROM evidence_records_legacy"
        )
        database.execute("DROP TABLE evidence_records_legacy")
        database.execute("DELETE FROM evidence_fts")
