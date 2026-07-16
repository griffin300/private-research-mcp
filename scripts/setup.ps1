[CmdletBinding()]
param([switch]$EnableBrowser)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is required.' }
docker info | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop Linux engine is not running.' }
docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is unavailable.' }

if (-not (Test-Path '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    Write-Host 'Created .env from .env.example.'
}
if (-not (Select-String -LiteralPath '.env' -Pattern '^SEARXNG_SECRET=' -Quiet)) {
    $secretBytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($secretBytes) } finally { $generator.Dispose() }
    $secret = ([BitConverter]::ToString($secretBytes) -replace '-', '').ToLowerInvariant()
    Add-Content -LiteralPath '.env' -Value "`nSEARXNG_SECRET=$secret"
    Write-Host 'Added a generated SearXNG secret to .env.'
} else {
    Write-Host 'Keeping existing SearXNG secret unchanged.'
}
if ($EnableBrowser) {
    $content = Get-Content -LiteralPath '.env' -Raw
    if ($content -match '(?m)^PRM_ENABLE_BROWSER=') {
        $content = $content -replace '(?m)^PRM_ENABLE_BROWSER=.*$', 'PRM_ENABLE_BROWSER=true'
    } else {
        $content += "`nPRM_ENABLE_BROWSER=true`n"
    }
    Set-Content -LiteralPath '.env' -Value $content -Encoding UTF8
    Write-Host 'Enabled the isolated browser fallback in .env.'
}

& "$PSScriptRoot\download-models.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Model setup failed.' }
docker compose build
if ($LASTEXITCODE -ne 0) { throw 'Container build failed.' }
$profileArgs = if ($EnableBrowser) { @('--profile', 'browser') } else { @() }
docker compose @profileArgs up -d
if ($LASTEXITCODE -ne 0) { throw 'Stack startup failed.' }
& "$PSScriptRoot\doctor.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Doctor checks failed.' }
docker compose exec -T app python -m mcp_bridge.smoke_test
if ($LASTEXITCODE -ne 0) { throw 'MCP smoke test failed.' }
docker compose exec -T app python -m mcp_bridge.live_smoke_test --url http://127.0.0.1:8088/mcp/
if ($LASTEXITCODE -ne 0) { throw 'Live search/read smoke test failed.' }
docker compose exec -T app python -m mcp_bridge.compound_smoke_test --url http://127.0.0.1:8088/mcp/
if ($LASTEXITCODE -ne 0) { throw 'Compound research smoke test failed.' }
& "$PSScriptRoot\privacy-test.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Privacy checks failed.' }
Write-Host 'Setup complete. Dashboard: http://127.0.0.1:8088/dashboard'
Write-Host 'LM Studio MCP URL: http://127.0.0.1:8088/mcp/'
