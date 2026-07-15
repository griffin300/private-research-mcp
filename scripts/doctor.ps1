$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$failures = 0
$warnings = 0
function Check($Name, [scriptblock]$Action) {
    try { & $Action | Out-Null; Write-Host "PASS $Name" -ForegroundColor Green }
    catch { $script:failures++; Write-Host "FAIL $Name - $($_.Exception.Message)" -ForegroundColor Red }
}
function Check-Optional($Name, [scriptblock]$Action) {
    try { & $Action | Out-Null; Write-Host "WARN $Name is available" -ForegroundColor Yellow }
    catch { $script:warnings++; Write-Host "WARN $Name - $($_.Exception.Message)" -ForegroundColor Yellow }
}
Check 'Docker engine' { docker info; if($LASTEXITCODE -ne 0){throw 'docker info failed'} }
Check 'Docker Compose' { docker compose version; if($LASTEXITCODE -ne 0){throw 'compose unavailable'} }
Check 'Compose configuration' { docker compose config --quiet; if($LASTEXITCODE -ne 0){throw 'invalid compose'} }
Check 'Application health' { $r=Invoke-RestMethod 'http://127.0.0.1:8088/health' -TimeoutSec 8; if($r.status -eq 'unhealthy'){throw 'unhealthy'} }
Check-Optional 'LM Studio endpoint (optional)' { Invoke-WebRequest 'http://127.0.0.1:1234/v1/models' -TimeoutSec 3 -UseBasicParsing }
Check 'Database integrity' { docker compose exec -T app python -c "from app.runtime import create_runtime; assert create_runtime().database.integrity()"; if($LASTEXITCODE -ne 0){throw 'database check failed'} }
Check 'Unsafe port exposure' { $c=docker compose config; if($c -match '0\.0\.0\.0:8088'){throw 'public bind detected'} }
Check 'Separate Tor gateways' { $c=docker compose config; if(-not($c -match 'tor-search' -and $c -match 'tor-fetch')){throw 'gateways missing'} }
if ($failures -gt 0) { Write-Host "$failures required checks failed." -ForegroundColor Red; exit 1 }
if ($warnings -gt 0) { Write-Host "$warnings optional checks unavailable." -ForegroundColor Yellow }
exit 0
