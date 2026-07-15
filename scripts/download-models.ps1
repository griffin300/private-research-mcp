[CmdletBinding()]
param([switch]$WithEmbeddings, [switch]$WithReranker)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ModelDir = Join-Path $Root 'models'
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
if (-not $WithEmbeddings -and -not $WithReranker) {
    Write-Host 'Lexical-only mode selected. No model downloads performed.'
    Write-Host 'Run download-models.ps1 -WithEmbeddings explicitly to install pinned local models.'
    exit 0
}
throw 'Model download manifest is intentionally disabled until exact upstream revisions and hashes are reviewed; runtime will not download models.'
