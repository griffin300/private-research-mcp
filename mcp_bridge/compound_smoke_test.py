from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _payload(value: dict[str, Any]) -> dict[str, Any]:
    result = value.get("result")
    return result if isinstance(result, dict) else value


def _safe_diagnostic(payload: dict[str, Any]) -> str:
    """Describe only fixed-test domains and aggregate failure classes."""
    domains = sorted(
        {
            str(source.get("domain", ""))
            for source in payload.get("sources", [])
            if isinstance(source, dict) and source.get("domain")
        }
    )
    failure_classes = Counter(
        f"{failure.get('stage', 'unknown')}:{failure.get('error', 'unknown')}"
        for failure in payload.get("failures", [])
        if isinstance(failure, dict)
    )
    failure_domains = sorted(
        {
            urlsplit(str(failure.get("url", ""))).hostname or ""
            for failure in payload.get("failures", [])
            if isinstance(failure, dict) and failure.get("url")
        }
        - {""}
    )
    facet_terms = {
        "python_stack": ("async", "stack"),
        "sqlite_wal": ("sqlite", "wal"),
        "mcp_http": ("streamable", "http"),
    }
    snippet_domains = {
        label: sorted(
            {
                str(snippet.get("domain", ""))
                for snippet in payload.get("search_snippets", [])
                if isinstance(snippet, dict)
                and all(
                    term in f"{snippet.get('title', '')} {snippet.get('text', '')}".casefold()
                    for term in terms
                )
                and snippet.get("domain")
            }
        )
        for label, terms in facet_terms.items()
    }
    return (
        f"source_domains={','.join(domains) or 'none'}; "
        f"snippet_domains={snippet_domains}; "
        f"failure_classes={dict(sorted(failure_classes.items()))}; "
        f"failure_domains={','.join(failure_domains) or 'none'}"
    )


async def smoke(url: str) -> None:
    query_batch = json.dumps(
        [
            "What does Python contextlib.AsyncExitStack do?",
            "How does SQLite WAL mode affect readers and writers?",
            "What is the MCP Streamable HTTP transport?",
        ]
    )
    started = time.monotonic()
    async with streamable_http_client(url) as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_web",
                {"query": query_batch, "mode": "auto", "max_sources": 8},
            )
    elapsed = time.monotonic() - started
    if result.isError or result.structuredContent is None:
        raise RuntimeError("compound live search failed")
    payload = _payload(result.structuredContent)
    warnings = payload.get("warnings", [])
    if not any("focused facets" in str(warning) for warning in warnings):
        raise RuntimeError("compound batch was not decomposed")
    snippets = payload.get("search_snippets", [])
    evidence = payload.get("evidence", [])
    if not isinstance(snippets, list) or not snippets:
        raise RuntimeError("compound live search returned no exact-result floor")
    snippet_text = " ".join(
        f"{snippet.get('title', '')} {snippet.get('text', '')}" for snippet in snippets
    ).casefold()
    for terms in (("async", "stack"), ("sqlite", "wal"), ("streamable", "http")):
        if not all(term in snippet_text for term in terms):
            raise RuntimeError("compound snippets did not preserve every focused facet")
    if not isinstance(evidence, list) or not evidence:
        raise RuntimeError("compound live search returned no extracted evidence")
    evidence_text = " ".join(str(item.get("text", "")) for item in evidence).casefold()
    evidence_checks = {
        "python_stack": ("async", "stack"),
        "sqlite_wal": ("sqlite", "wal"),
        "mcp_http": ("streamable", "http"),
    }
    missing_evidence = [
        label
        for label, terms in evidence_checks.items()
        if not all(term in evidence_text for term in terms)
    ]
    if missing_evidence:
        raise RuntimeError(
            f"compound evidence missed facets: {','.join(missing_evidence)}; "
            f"{_safe_diagnostic(payload)}"
        )
    if payload.get("coverage", {}).get("missing_topics"):
        raise RuntimeError("compound live search left a focused facet uncovered")
    if any("deadline" in str(warning).casefold() for warning in warnings):
        raise RuntimeError("compound live search reached its server deadline")
    if elapsed >= 180:
        raise RuntimeError(f"compound live search exceeded latency target: {elapsed:.2f}s")
    print(f"PASS: compound search completed in {elapsed:.2f}s")
    print(
        "PASS: "
        f"{len(snippets)} snippets, {len(payload.get('sources', []))} sources, "
        f"{len(evidence)} evidence passages, "
        f"coverage={payload.get('coverage', {}).get('score', 0)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test explicit query-batch repair")
    parser.add_argument("--url", default="http://127.0.0.1:8088/mcp/")
    args = parser.parse_args()
    asyncio.run(smoke(args.url))


if __name__ == "__main__":
    main()
