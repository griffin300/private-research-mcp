$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
docker compose down
Write-Host 'Private Research MCP stopped. The data volume was preserved.'

