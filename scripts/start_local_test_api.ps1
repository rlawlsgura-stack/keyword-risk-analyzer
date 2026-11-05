$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repoRoot '.env.test.local'
$python = Join-Path $repoRoot '.venv-ocr313\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw 'Create .env.test.local from .env.test.example and fill only local Supabase values first.'
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'The .venv-ocr313 Python environment was not found. Create the Python 3.13 OCR environment first.'
}
& $python -c "import paddleocr, paddle, paddlex"
if ($LASTEXITCODE -ne 0) {
    throw 'OCR dependencies are missing from .venv-ocr313. Install requirements-ocr.txt into that environment.'
}

$settings = @{}
foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -match '^\s*([^#=\s]+)\s*=(.*)$') {
        $settings[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
    }
}

if ($settings['STORAGE_BACKEND'] -ne 'supabase') {
    throw 'The isolated API requires STORAGE_BACKEND=supabase.'
}
if ($settings['SUPABASE_ALLOW_LOCAL_HTTP'] -ne '1') {
    throw 'The isolated API requires SUPABASE_ALLOW_LOCAL_HTTP=1.'
}
if ([string]::IsNullOrWhiteSpace($settings['SUPABASE_SECRET_KEY'])) {
    throw 'Fill SUPABASE_SECRET_KEY with the local Supabase service key; do not use a production key.'
}
if (-not [string]::IsNullOrWhiteSpace($settings['API_ACCESS_TOKEN'])) {
    throw 'Leave API_ACCESS_TOKEN empty so a production integration token cannot enter the test API.'
}

try {
    $databaseUri = [Uri]$settings['SUPABASE_URL']
} catch {
    throw 'SUPABASE_URL is invalid. It must point to the local Supabase stack.'
}
if ($databaseUri.Scheme -ne 'http' -or -not $databaseUri.IsLoopback) {
    throw 'Refusing to start: SUPABASE_URL must use HTTP on localhost/loopback.'
}

$env:KRA_ENV_FILE = $envFile
& $python -m uvicorn api:app --app-dir $repoRoot --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
