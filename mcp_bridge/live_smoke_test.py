from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _payload(value: dict[str, Any]) -> dict[str, Any]:
    result = value.get("result")
    return result if isinstance(result, dict) else value


async def smoke(url: str) -> None:
    async with streamable_http_client(url) as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            search_result = await session.call_tool(
                "search_web",
                {
                    "query": "official Model Context Protocol Python SDK",
                    "mode": "quick",
                    "max_sources": 3,
                    "include_domains": ["github.com"],
                },
            )
            if search_result.isError or search_result.structuredContent is None:
                raise RuntimeError("live search_web call failed")
            search = _payload(search_result.structuredContent)
            evidence = search.get("evidence", [])
            if not isinstance(evidence, list) or not evidence:
                raise RuntimeError(
                    f"live search returned no evidence; failures={search.get('failures')}"
                )
            search_chars = len(json.dumps(search, ensure_ascii=False))
            if search.get("response_info", {}).get("detail") != "compact":
                raise RuntimeError("live search did not return compact response detail")
            if search_chars > 9_000:
                raise RuntimeError(f"live quick response exceeded 9,000 chars: {search_chars}")

            repeated_result = await session.call_tool(
                "search_web",
                {
                    "query": "Repeat the preceding search immediately",
                    "mode": "quick",
                },
            )
            if repeated_result.isError or repeated_result.structuredContent is None:
                raise RuntimeError("repeat-search guard call failed")
            repeated = _payload(repeated_result.structuredContent)
            if repeated.get("status") != "repeated_search_suppressed":
                raise RuntimeError("immediate repeated search was not suppressed")

            read_result = await session.call_tool(
                "read_url",
                {
                    "url": "https://github.com/modelcontextprotocol/python-sdk",
                    "question": "What is this repository?",
                },
            )
            if read_result.isError or read_result.structuredContent is None:
                raise RuntimeError("live read_url call failed")
            read = _payload(read_result.structuredContent)
            passages = read.get("passages", [])
            if not isinstance(passages, list) or not passages:
                raise RuntimeError(f"live read returned no passages: {read}")
            read_chars = len(json.dumps(read, ensure_ascii=False))
            if read.get("response_info", {}).get("detail") != "compact":
                raise RuntimeError("live read did not return compact response detail")
            if read_chars > 10_000:
                raise RuntimeError(f"live read exceeded 10,000 chars: {read_chars}")

            print(
                f"PASS: search_web returned {len(evidence)} evidence passages "
                f"in {search_chars} chars"
            )
            print("PASS: immediate repeated search was suppressed")
            print(f"PASS: read_url returned {len(passages)} ranked passages in {read_chars} chars")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live search and read MCP smoke tests")
    parser.add_argument("--url", default="http://127.0.0.1:8088/mcp/")
    args = parser.parse_args()
    asyncio.run(smoke(args.url))


if __name__ == "__main__":
    main()
