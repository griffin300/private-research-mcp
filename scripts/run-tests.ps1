$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
docker build --target base -t private-research-test .
docker run --rm --network none -v "${Root}:/src:ro" private-research-test sh -lc 'cp -a /src /tmp/project && cd /tmp/project && uv sync --extra dev && uv run ruff check . && uv run ruff format --check . && uv run mypy app mcp_bridge && uv run pytest -m "not privacy and not live"'
& "$PSScriptRoot\privacy-test.ps1"
