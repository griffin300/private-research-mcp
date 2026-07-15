[CmdletBinding()]
param([switch]$EnableBrowser)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$profileArgs = if ($EnableBrowser) { @('--profile', 'browser') } else { @() }
if ($EnableBrowser) {
    $content = Get-Content -LiteralPath '.env' -Raw
    if ($content -notmatch '(?m)^PRM_ENABLE_BROWSER=true$') {
        throw 'Run scripts/setup.ps1 -EnableBrowser first so the app and browser profile are enabled together.'
    }
}
docker compose @profileArgs up -d
docker compose ps
$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8088/health' -TimeoutSec 10
if ($health.status -eq 'unhealthy') { throw 'Stack started but reports unhealthy.' }
Write-Host "Started: http://127.0.0.1:8088/dashboard ($($health.status))"
