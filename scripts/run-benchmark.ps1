$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
docker compose exec -T app python -m benchmarks.evaluate
Write-Host 'Report: benchmarks/results/latest-report.md'

