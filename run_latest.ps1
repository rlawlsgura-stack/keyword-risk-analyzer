param(
    [int]$Port = 8501
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonCandidates = @(
    (Join-Path $projectRoot '.venv-ocr313\Scripts\python.exe'),
    (Join-Path $projectRoot '.venv\Scripts\python.exe')
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Project virtual environment not found. Create .venv-ocr313 or .venv first.'
}

$preflight = Join-Path $projectRoot 'scripts\check_supabase_connectivity.py'
& $python $preflight
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$latest = Get-ChildItem -LiteralPath $projectRoot -Filter 'keyword_app2_fixed*.py' -File |
    Where-Object { $_.BaseName -match '^keyword_app2_fixed\d+$' } |
    Sort-Object -Property @{ Expression = { [int]($_.BaseName -replace '^keyword_app2_fixed', '') }; Descending = $true } |
    Select-Object -First 1

if (-not $latest) {
    throw 'No keyword_app2_fixed###.py application file was found.'
}

Write-Host "Starting $($latest.Name) at http://localhost:$Port"
& $python -m streamlit run $latest.FullName --server.address=127.0.0.1 --server.port=$Port --server.headless=true
