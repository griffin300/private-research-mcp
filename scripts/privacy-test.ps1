$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$failures = 0

function Test-Privacy($Name, [scriptblock]$Action) {
    try {
        & $Action | Out-Null
        Write-Host "PASS $Name" -ForegroundColor Green
    } catch {
        $script:failures++
        Write-Host "FAIL $Name - $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Get-Container($Name) {
    $raw = docker inspect $Name
    if ($LASTEXITCODE -ne 0) { throw "cannot inspect $Name" }
    return ($raw | ConvertFrom-Json)[0]
}

function Write-PrivacyStatus($Result) {
    $checkedAt = [DateTimeOffset]::UtcNow.ToString('o')
    $code = "import json,sys; from pathlib import Path; Path('/data/privacy-status.json').write_text(json.dumps({'result':sys.argv[1],'checked_at':sys.argv[2]}),encoding='utf-8')"
    docker compose exec -T app python -c $code $Result $checkedAt | Out-Null
}

Test-Privacy 'Compose validates' {
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'invalid Compose configuration' }
}
Test-Privacy 'Required containers are running and healthy' {
    foreach ($name in @(
        'private-research-mcp-tor-search-1',
        'private-research-mcp-tor-fetch-1',
        'private-research-mcp-searxng-1',
        'private-research-mcp-app-1',
        'private-research-mcp-mcp-bridge-1'
    )) {
        $container = Get-Container $name
        if (-not $container.State.Running) { throw "$name is not running" }
        if ($container.State.Health -and $container.State.Health.Status -ne 'healthy') {
            throw "$name is $($container.State.Health.Status)"
        }
    }
}
Test-Privacy 'Internal network is marked internal' {
    $raw = docker network inspect private-research-mcp_internal_private
    if ($LASTEXITCODE -ne 0) { throw 'network inspect failed' }
    $network = ($raw | ConvertFrom-Json)[0]
    if (-not $network.Internal) { throw 'internal_private is not internal' }
}
Test-Privacy 'App only joins internal network' {
    $container = Get-Container 'private-research-mcp-app-1'
    $names = @($container.NetworkSettings.Networks.PSObject.Properties.Name)
    if ($names.Count -ne 1 -or $names[0] -notmatch 'internal_private') {
        throw ($names -join ',')
    }
}
Test-Privacy 'SearXNG only joins internal network' {
    $container = Get-Container 'private-research-mcp-searxng-1'
    $names = @($container.NetworkSettings.Networks.PSObject.Properties.Name)
    if ($names.Count -ne 1 -or $names[0] -notmatch 'internal_private') {
        throw ($names -join ',')
    }
}
Test-Privacy 'Search and fetch gateways are separate' {
    $search = Get-Container 'private-research-mcp-tor-search-1'
    $fetch = Get-Container 'private-research-mcp-tor-fetch-1'
    if ($search.Id -eq $fetch.Id) { throw 'same gateway container' }
}
Test-Privacy 'No public app bind' {
    $appPorts = (Get-Container 'private-research-mcp-app-1').NetworkSettings.Ports.'8088/tcp'
    if ($appPorts.Count -ne 0) { throw 'app is published directly' }
    $port = docker port private-research-mcp-mcp-bridge-1 8088/tcp
    if ($LASTEXITCODE -ne 0) { throw 'loopback bridge port is not published' }
    if ($port -notmatch '^127\.0\.0\.1:') { throw $port }
}
Test-Privacy 'Loopback bridge cannot directly reach public IPs' {
    $result = docker compose exec -T mcp-bridge sh -c "nc -z -w 2 1.1.1.1 443 && echo REACHABLE || echo BLOCKED"
    if ($LASTEXITCODE -ne 0) { throw 'bridge egress probe did not execute' }
    if ($result -notmatch 'BLOCKED') { throw 'loopback bridge has direct egress' }
}
Test-Privacy 'Unprivileged loopback bridge cannot use Docker DNS for public names' {
    $result = docker compose exec -T --user bridge mcp-bridge sh -c "getent hosts example.com >/dev/null 2>&1 && echo RESOLVED || echo BLOCKED"
    if ($LASTEXITCODE -ne 0) { throw 'bridge DNS probe did not execute' }
    if ($result -notmatch 'BLOCKED') { throw 'network-facing bridge user resolved public DNS' }
}
Test-Privacy 'Raw query logging disabled' {
    $value = docker compose exec -T app python -c "from app.config import Settings; print(Settings().log_raw_queries)"
    if ($LASTEXITCODE -ne 0) { throw 'could not read runtime setting' }
    if ($value -notmatch 'False') { throw 'raw query logging enabled' }
}
Test-Privacy 'Runtime privacy settings are launch-safe' {
    $code = "from app.config import Settings; s=Settings(); print(s.privacy_mode, s.store_search_history, s.allow_private_destinations)"
    $value = docker compose exec -T app python -c $code
    if ($LASTEXITCODE -ne 0) { throw 'could not read runtime privacy settings' }
    if ($value -notmatch '^strict False False$') {
        throw "unsafe runtime privacy settings: $value"
    }
}
Test-Privacy 'Query-bearing SearXNG container logs are disabled' {
    $container = Get-Container 'private-research-mcp-searxng-1'
    if ($container.HostConfig.LogConfig.Type -ne 'none') {
        throw "SearXNG logging driver is $($container.HostConfig.LogConfig.Type)"
    }
}
Test-Privacy 'URL-bearing HTTP client logs are suppressed' {
    $code = "import logging; from app.logging_config import configure_logging; configure_logging('INFO'); print(logging.getLogger('httpx').getEffectiveLevel(), logging.getLogger('httpcore').getEffectiveLevel())"
    $value = docker compose exec -T app python -c $code
    if ($LASTEXITCODE -ne 0) { throw 'could not inspect runtime logger levels' }
    if ($value -notmatch '50 50') { throw "unsafe logger levels: $value" }
}
Test-Privacy 'No cloud API configuration' {
    $hits = rg -n -i 'api\.(openai|anthropic)\.com|api\.tavily\.com|api\.exa\.ai' app config docker-compose.yml .env.example
    if ($LASTEXITCODE -eq 0) { throw $hits }
    if ($LASTEXITCODE -ne 1) { throw 'configuration scan failed' }
}
Test-Privacy 'Direct public IP egress blocked from app' {
    $result = docker compose exec -T app python -c "import socket; s=socket.socket(); s.settimeout(2); print('BLOCKED' if s.connect_ex(('1.1.1.1',443)) != 0 else 'REACHABLE')"
    if ($LASTEXITCODE -ne 0) { throw 'egress probe did not execute' }
    if ($result -notmatch 'BLOCKED') { throw 'public IP was directly reachable' }
}
Test-Privacy 'Direct public DNS resolution blocked from app' {
    $result = docker compose exec -T app python -c "import socket;`ntry: socket.getaddrinfo('example.com',443); print('RESOLVED')`nexcept socket.gaierror: print('BLOCKED')"
    if ($LASTEXITCODE -ne 0) { throw 'DNS probe did not execute' }
    if ($result -notmatch 'BLOCKED') { throw 'public DNS resolved outside SOCKS' }
}
$browserName = 'private-research-mcp-browser-service-1'
$browserPresent = (docker ps --format '{{.Names}}') -contains $browserName
if ($browserPresent) {
    Test-Privacy 'Browser only joins the internal network' {
        $container = Get-Container $browserName
        $names = @($container.NetworkSettings.Networks.PSObject.Properties.Name)
        if (-not $container.State.Running -or $names.Count -ne 1 -or $names[0] -notmatch 'internal_private') {
            throw ($names -join ',')
        }
    }
    Test-Privacy 'Browser direct IP and DNS egress are blocked' {
        $ip = docker compose exec -T browser-service python -c "import socket; s=socket.socket(); s.settimeout(2); print('BLOCKED' if s.connect_ex(('1.1.1.1',443)) != 0 else 'REACHABLE')"
        if ($LASTEXITCODE -ne 0 -or $ip -notmatch 'BLOCKED') { throw 'browser reached a public IP directly' }
        $dns = docker compose exec -T browser-service python -c "import socket;`ntry: socket.getaddrinfo('example.com',443); print('RESOLVED')`nexcept socket.gaierror: print('BLOCKED')"
        if ($LASTEXITCODE -ne 0 -or $dns -notmatch 'BLOCKED') { throw 'browser resolved public DNS directly' }
    }
    Test-Privacy 'Browser rendering uses tor-fetch' {
        $code = "import httpx; d=httpx.post('http://browser-service:8090/render',json={'url':'https://check.torproject.org/api/ip'},timeout=60).json(); h=d['html'].lower(); print('TOR' if 'istor' in h and 'true' in h else 'NOT_TOR')"
        $result = docker compose exec -T app python -c $code
        if ($LASTEXITCODE -ne 0 -or $result -notmatch '^TOR$') { throw 'browser Tor render probe failed' }
    }
}
Test-Privacy 'Search and fetch use distinct Tor exits' {
    $code = "import json,httpx; u='https://check.torproject.org/api/ip'; a=httpx.get(u,proxy='socks5://tor-search:9050',timeout=30).json(); b=httpx.get(u,proxy='socks5://tor-fetch:9050',timeout=30).json(); print(json.dumps({'search':a['IP'],'fetch':b['IP'],'search_tor':a['IsTor'],'fetch_tor':b['IsTor']}))"
    $raw = docker compose exec -T app python -c $code
    if ($LASTEXITCODE -ne 0) { throw 'Tor exit probe failed' }
    $result = $raw | ConvertFrom-Json
    if (-not $result.search_tor -or -not $result.fetch_tor) { throw 'non-Tor exit observed' }
    if ($result.search -eq $result.fetch) { throw 'search and fetch used the same exit IP' }
}

try {
    docker compose stop tor-fetch | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'could not stop tor-fetch' }
    $probeUrl = "https://example.com/privacy-probe-$([Guid]::NewGuid().ToString('N'))"
    $code = "import asyncio; from app.runtime import create_runtime;`nasync def p():`n try: await create_runtime().pipeline.read_url('$probeUrl'); print('UNSAFE_SUCCESS')`n except Exception: print('BLOCKED')`nasyncio.run(p())"
    $result = docker compose exec -T app python -c $code
    if ($LASTEXITCODE -ne 0) { throw 'fail-closed probe did not execute' }
    if ($result -notmatch 'BLOCKED') { throw 'fetch succeeded after tor-fetch stopped' }
    Write-Host 'PASS Tor failure is fail-closed' -ForegroundColor Green
} catch {
    $failures++
    Write-Host "FAIL Tor failure is fail-closed - $($_.Exception.Message)" -ForegroundColor Red
} finally {
    docker compose start tor-fetch | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $failures++
        Write-Host 'FAIL tor-fetch recovery' -ForegroundColor Red
    } else {
        $healthy = $false
        for ($i = 0; $i -lt 20; $i++) {
            $container = Get-Container 'private-research-mcp-tor-fetch-1'
            if ($container.State.Health.Status -eq 'healthy') { $healthy = $true; break }
            Start-Sleep -Seconds 2
        }
        if (-not $healthy) {
            $failures++
            Write-Host 'FAIL tor-fetch recovery health' -ForegroundColor Red
        }
    }
}

if ($failures) {
    Write-PrivacyStatus 'FAIL'
    Write-Host "PRIVACY TEST RESULT: FAIL ($failures)" -ForegroundColor Red
    exit 1
}
Write-PrivacyStatus 'PASS'
Write-Host 'PRIVACY TEST RESULT: PASS' -ForegroundColor Green
exit 0
