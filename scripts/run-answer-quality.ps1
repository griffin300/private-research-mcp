$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
docker compose exec -T app python -m benchmarks.answer_quality
if ($LASTEXITCODE -ne 0) { throw 'Answer-quality benchmark failed.' }
& .\.venv\Scripts\python.exe -m benchmarks.synthesize_answers
if ($LASTEXITCODE -ne 0) { throw 'Local answer synthesis benchmark failed.' }
Write-Host 'Retrieval report: benchmarks/results/latest-answer-quality-report.md'
Write-Host 'Answer report: benchmarks/results/latest-synthesized-answer-report.md'
