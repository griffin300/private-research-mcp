from __future__ import annotations

import argparse
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def smoke(url: str) -> None:
    async with streamable_http_client(url) as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            expected = {
                "search_web",
                "deep_research",
                "read_url",
                "search_status",
                "clear_local_data",
            }
            missing = expected - names
            if missing:
                raise RuntimeError(f"missing MCP tools: {sorted(missing)}")

            status = await session.call_tool("search_status", {})
            if status.isError or status.structuredContent is None:
                raise RuntimeError("search_status did not return structured MCP content")

            print("PASS: Streamable HTTP MCP initialized")
            print(f"PASS: all required tools are present: {', '.join(sorted(expected))}")
            print("PASS: search_status returned structured content")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the Streamable HTTP MCP endpoint")
    parser.add_argument("--url", default="http://127.0.0.1:8088/mcp/")
    args = parser.parse_args()
    asyncio.run(smoke(args.url))


if __name__ == "__main__":
    main()
