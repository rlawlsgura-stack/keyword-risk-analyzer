$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot 'frontend'
$envFile = Join-Path $frontendRoot '.env.test.local'
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw 'Run scripts/start_local_test_supabase.ps1 first to create the local-only frontend settings.'
}

$settings = @{}
foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -match '^\s*([^#=\s]+)\s*=(.*)$') {
        $settings[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
    }
}

foreach ($name in @('VITE_SUPABASE_URL', 'VITE_SUPABASE_PUBLISHABLE_KEY', 'VITE_API_BASE_URL')) {
    if ([string]::IsNullOrWhiteSpace($settings[$name])) {
        throw "The local frontend setting $name is missing. Run scripts/start_local_test_supabase.ps1 again."
    }
}

foreach ($name in @('VITE_SUPABASE_URL', 'VITE_API_BASE_URL')) {
    $uri = [Uri]$settings[$name]
    if ($uri.Scheme -ne 'http' -or -not $uri.IsLoopback) {
        throw "Refusing to start: $name must point to a loopback HTTP address."
    }
}
if (([Uri]$settings['VITE_SUPABASE_URL']).Port -ne 54321 -or
    ([Uri]$settings['VITE_API_BASE_URL']).Port -ne 8000) {
    throw 'Refusing to start: frontend settings must use local Supabase :54321 and local API :8000.'
}

$env:VITE_SUPABASE_URL = $settings['VITE_SUPABASE_URL']
$env:VITE_SUPABASE_PUBLISHABLE_KEY = $settings['VITE_SUPABASE_PUBLISHABLE_KEY']
$env:VITE_API_BASE_URL = $settings['VITE_API_BASE_URL']
Push-Location $frontendRoot
try {
    npm run dev -- --mode test --host 127.0.0.1
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
