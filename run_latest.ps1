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

$entrypoint = Join-Path $projectRoot 'streamlit_cloud\app.py'
if (-not (Test-Path -LiteralPath $entrypoint)) {
    throw 'Shared app entrypoint not found: streamlit_cloud\app.py'
}

Write-Host "Starting the shared latest-version entrypoint at http://localhost:$Port"
& $python -m streamlit run $entrypoint --server.address=127.0.0.1 --server.port=$Port --server.headless=true
