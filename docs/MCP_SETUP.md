# LM Studio MCP setup

## Preferred: Streamable HTTP

Start the stack:

```powershell
.\scripts\start.ps1
```

In LM Studio 0.3.17+, open **Program → Install → Edit mcp.json** and merge:

```json
{
  "mcpServers": {
    "private-research": {
      "url": "http://127.0.0.1:8088/mcp/",
      "timeout": 900000
    }
  }
}
```

Do not add proxy credentials or secrets. Save and enable the server. Expected tools: `search_web`, `deep_research`, `read_url`, `search_status`, `clear_local_data`. First call `search_status`; expected service/database status is healthy and `unsafe_fallback_enabled` is false.

LM Studio currently uses Cursor-style `mcp.json` notation and supports local/remote MCP servers. Streamable HTTP is the production transport recommended by stable MCP Python SDK documentation.

## Stdio bridge

Stdio is useful if the host has Python 3.12 and `uv` installed. Add:

```json
{
  "mcpServers": {
    "private-research-stdio": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "C:\\absolute\\path\\to\\private-research-mcp",
        "python",
        "-m",
        "mcp_bridge"
      ],
      "env": {
        "PRM_DATABASE_PATH": "C:\\absolute\\path\\to\\private-research-mcp\\data\\research.db",
        "PRM_SEARXNG_BASE_URL": "http://127.0.0.1:8080"
      }
    }
  }
}
```

The bundled SearXNG is intentionally not host-published, so stdio is mainly for development with a separately configured private SearXNG. Use Streamable HTTP for the bundled stack.

## Smoke test

```powershell
docker compose exec -T app python -m mcp_bridge.smoke_test
```

Expected output:

```text
PASS: MCP initialized and all required tools are present
```

To verify the loopback Streamable HTTP endpoint from the host:

```powershell
.\.venv\Scripts\python.exe -m mcp_bridge.http_smoke_test
```

With the stack online, verify a real private search and page read:

```powershell
.\.venv\Scripts\python.exe -m mcp_bridge.live_smoke_test
```

## LM Studio API use

LM Studio 0.4.0+ can expose configured `mcp.json` servers to API clients. Enable **Require Authentication** and **Allow calling servers from mcp.json**, then use integration ID `mcp/private-research`. Keep **Serve on Local Network** disabled unless explicitly required.

## Troubleshooting

- Connection refused: run `Invoke-RestMethod http://127.0.0.1:8088/health`.
- Request timed out (`-32001`): confirm the server entry has `"timeout": 900000`; the app returns completed partial research at its shorter mode-specific deadline instead of leaving orphaned work running.
- 404 or redirect trouble: use the canonical URL `http://127.0.0.1:8088/mcp/`.
- Tools absent: reload `mcp.json` and ensure the JSON is nested under `mcpServers`.
- Calls fail but tools list: run `search_status`, then inspect `docker compose logs app tor-search tor-fetch`. SearXNG container logs are deliberately disabled to prevent engine errors from recording query URLs.
- Do not point the optional planner at the same single-slot model. It is disabled unless a separate local endpoint/model is explicitly configured.
