from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def smoke() -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_bridge"],
        env={
            **os.environ,
            "PRM_DATABASE_PATH": os.environ.get("PRM_DATABASE_PATH", "data/research.db"),
        },
    )
    async with stdio_client(parameters) as (reader, writer):
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
            print("PASS: MCP initialized and all required tools are present")


if __name__ == "__main__":
    asyncio.run(smoke())
