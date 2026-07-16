from datetime import UTC, datetime

from app.models import SearchResult
from app.ranking.freshness import freshness_score
from app.ranking.source_quality import score_search_result, source_type
from app.search.official_sources import (
    authority_search_variant,
    distinctive_query_tokens,
    domain_matches_authority,
    official_source_candidates,
)
from app.search.searxng import _categories_for_query


def test_known_identifiers_derive_bounded_canonical_sources() -> None:
    python = official_source_candidates("On what date was Python 3.12.0 released?")
    assert [item.url for item in python] == [
        "https://www.python.org/downloads/release/python-3120/"
    ]
    mcp = official_source_candidates(
        "According to the official MCP Python SDK, which transport is for production?"
    )
    assert [item.url for item in mcp] == [
        "https://py.sdk.modelcontextprotocol.io/server/",
        "https://raw.githubusercontent.com/modelcontextprotocol/"
        "python-sdk/v1.x/docs/server.md",
    ]
    assert all(item.engine == "deterministic_official_source" for item in [*python, *mcp])
    sqlite = official_source_candidates(
        "In SQLite, what reader/writer concurrency does WAL mode permit?"
    )
    assert [item.url for item in sqlite] == ["https://www.sqlite.org/wal.html"]
    status = official_source_candidates("What does HTTP status code 429 mean?")
    assert status[0].url.startswith("https://www.iana.org/assignments/http-status-codes/")
    ipv4 = official_source_candidates("Which RFC defines the private IPv4 address blocks?")
    assert "iana-ipv4-special-registry" in ipv4[0].url
    identifiers = official_source_candidates("Compare RFC 9110 with PEP 8")
    assert {item.url for item in identifiers} == {
        "https://www.rfc-editor.org/rfc/rfc9110.html",
        "https://peps.python.org/pep-0008/",
    }


def test_direct_release_and_sdk_candidates_require_matching_intent() -> None:
    generic_client = "What does the MCP Python SDK client do?"
    generic_timeout = "How to fix an MCP Python SDK client timeout?"
    mcp_advisory = "Is the MCP Python SDK client affected by CVE-2026-12345?"
    python_advisory = "Is Python 3.12.0 affected by CVE-2025-99999?"
    python_runtime = "How does memory allocation work in Python 3.12.0?"

    assert official_source_candidates(generic_client) == []
    assert official_source_candidates(generic_timeout) == []
    assert official_source_candidates(mcp_advisory) == []
    assert official_source_candidates(python_advisory) == []
    assert official_source_candidates(python_runtime) == []
    assert authority_search_variant(generic_client) is None
    assert authority_search_variant(generic_timeout) is None
    assert authority_search_variant(mcp_advisory) is None
    assert authority_search_variant(python_advisory) is None


def test_sdk_documentation_routes_to_topic_specific_canonical_pages() -> None:
    client = official_source_candidates(
        "According to the official MCP Python SDK client docs, how do clients connect?"
    )
    installation = official_source_candidates(
        "How to install the MCP Python SDK according to its documentation?"
    )
    release = official_source_candidates("When was Python 3.13.2 released?")
    feature = official_source_candidates(
        "According to the official MCP Python SDK, how are structured outputs represented?"
    )

    assert [item.url for item in client] == ["https://py.sdk.modelcontextprotocol.io/client/"]
    assert [item.url for item in installation] == [
        "https://py.sdk.modelcontextprotocol.io/installation/"
    ]
    assert [item.url for item in release] == [
        "https://www.python.org/downloads/release/python-3132/"
    ]
    assert [item.url for item in feature] == ["https://py.sdk.modelcontextprotocol.io/"]
    assert "v1.x" not in " ".join(item.url for item in [*client, *installation])


def test_explicit_github_repository_authority_is_exact_path_scoped() -> None:
    query = (
        "Inspect the GitHub repository https://github.com/Pallets/Flask/tree/main/src source code"
    )
    candidates = official_source_candidates(query)

    assert [item.url for item in candidates] == ["https://github.com/Pallets/Flask"]
    assert domain_matches_authority(query, "https://github.com/Pallets/Flask")
    assert domain_matches_authority(query, "https://github.com/Pallets/Flask/tree/main/src")
    assert not domain_matches_authority(query, "https://github.com/pallets/flask-security")
    assert not domain_matches_authority(query, "https://github.com/psf/requests")
    assert not domain_matches_authority(
        "MCP Python SDK client timeout", "https://github.com/random/mcp-client"
    )


def test_mcp_raw_documentation_authority_is_repository_scoped() -> None:
    query = "According to the official MCP Python SDK, which transport is for production?"

    assert domain_matches_authority(
        query,
        "https://raw.githubusercontent.com/modelcontextprotocol/"
        "python-sdk/v1.x/docs/server.md",
    )
    assert not domain_matches_authority(
        query,
        "https://raw.githubusercontent.com/unrelated/project/main/server.md",
    )
    assert source_type(
        "https://raw.githubusercontent.com/modelcontextprotocol/"
        "python-sdk/v1.x/docs/server.md"
    ) == "official_documentation"


def test_numeric_anchors_require_typed_identifier_context() -> None:
    assert (
        distinctive_query_tokens(
            "Compare 2026 prices of $1.99 across 500 products in three regions"
        )
        == set()
    )
    anchors = distinctive_query_tokens(
        "Compare RFC 9110, HTTP status 429, Python 3.13.2, and CVE-2025-12345"
    )
    assert {"9110", "429", "3.13.2", "cve-2025-12345"} <= anchors


def test_query_aligned_primary_source_outranks_generic_documentation() -> None:
    query = "On what date was Python 3.12.0 released?"
    official = SearchResult(
        url="https://www.python.org/downloads/release/python-3120/",
        title="Python 3.12.0 official release",
        search_score=0.8,
    )
    generic = SearchResult(
        url="https://developer.mozilla.org/en-US/docs/Glossary/Python",
        title="Python",
        search_score=1.0,
    )
    assert score_search_result(query, official) > score_search_result(query, generic)
    assert source_type(official.url) == "official_documentation"


def test_reference_queries_avoid_noisy_it_verticals() -> None:
    assert _categories_for_query("Python 3.12.0 release date") == "general"
    assert _categories_for_query("MCP protocol transport documentation") == "general"
    assert _categories_for_query("Python traceback package install failed") == "general,it"


def test_stable_fact_freshness_does_not_age_decay_primary_sources() -> None:
    old = datetime(1996, 2, 1, tzinfo=UTC)
    recent = datetime.now(UTC)
    assert freshness_score(old, time_sensitive=False) == freshness_score(
        recent, time_sensitive=False
    )
    assert freshness_score(old, time_sensitive=True) < freshness_score(recent, time_sensitive=True)
