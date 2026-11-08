$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot 'frontend'
$networkName = 'kra-local-loopback'
$cli = Join-Path $frontendRoot 'node_modules\.bin\supabase.cmd'
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw 'The pinned Supabase CLI is missing. Run npm ci in frontend first.'
}

$null = docker info --format '{{.ServerVersion}}' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Desktop is not running. Start Docker Desktop, then rerun this script.'
}
$firewallProfiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore)
if ($firewallProfiles.Count -lt 3 -or
    @($firewallProfiles | Where-Object { -not $_.Enabled -or $_.DefaultInboundAction -ne 'Block' }).Count -gt 0) {
    throw 'Refusing to start: enable Windows Firewall and block inbound connections on every profile first.'
}

$networkNames = @(docker network ls --format '{{.Name}}')
if ($networkNames -notcontains $networkName) {
    $null = docker network create --driver bridge --opt 'com.docker.network.bridge.host_binding_ipv4=127.0.0.1' $networkName
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the loopback-only Docker network.' }
}
$existingNetwork = docker network inspect $networkName | ConvertFrom-Json
$binding = $existingNetwork[0].Options.'com.docker.network.bridge.host_binding_ipv4'
if ($binding -ne '127.0.0.1') {
    throw "Refusing to start: Docker network $networkName is not configured for loopback access."
}

Push-Location $frontendRoot
try {
    # This command targets only the local stack; no Supabase project is linked or contacted.
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue' # Docker progress is written to stderr on Windows.
    try {
        $startOutput = & $cli --workdir $repoRoot start --network-id $networkName --exclude 'vector,logflare,edge-runtime,imgproxy,supavisor' 2>&1
        $startExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
    if ($startExitCode -ne 0) {
        foreach ($line in $startOutput) {
            $safe = [string]$line
            if ($safe -notmatch '(?i)(secret|service.role|anon.key|publishable.key|jwt|postgres(ql)?://|password)') {
                Write-Error $safe -ErrorAction Continue
            }
        }
        throw 'Local Supabase did not start. Check Docker Desktop and rerun this script.'
    }

    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $statusOutput = & $cli --workdir $repoRoot status --output env 2>&1
        $statusExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
    if ($statusExitCode -ne 0) { throw 'Could not read local Supabase status.' }
    $status = @{}
    foreach ($line in $statusOutput) {
        if ([string]$line -match '^\s*([A-Z_]+)="?([^"\r\n]*)"?\s*$') {
            $status[$Matches[1]] = $Matches[2]
        }
    }

    $apiUrl = $status['API_URL']
    if (-not $apiUrl) { $apiUrl = $status['SUPABASE_URL'] }
    $anonKey = $status['ANON_KEY']
    if (-not $anonKey) { $anonKey = $status['PUBLISHABLE_KEY'] }
    $serviceKey = $status['SERVICE_ROLE_KEY']
    if (-not $serviceKey) { $serviceKey = $status['SECRET_KEY'] }
    if (-not $apiUrl -or -not $anonKey -or -not $serviceKey) {
        throw 'Local Supabase status did not provide the expected local API and authentication keys.'
    }
    $apiUri = [Uri]$apiUrl
    if ($apiUri.Scheme -ne 'http' -or -not $apiUri.IsLoopback -or $apiUri.Port -ne 54321) {
        throw 'Refusing to write settings: the Supabase CLI did not report local loopback :54321.'
    }

    $backendFile = Join-Path $repoRoot '.env.test.local'
    @(
        'STORAGE_BACKEND=supabase'
        "SUPABASE_URL=$apiUrl"
        "SUPABASE_SECRET_KEY=$serviceKey"
        'SUPABASE_ALLOW_LOCAL_HTTP=1'
        'API_ACCESS_TOKEN='
    ) | Set-Content -LiteralPath $backendFile -Encoding utf8

    $frontendFile = Join-Path $frontendRoot '.env.test.local'
    @(
        "VITE_SUPABASE_URL=$apiUrl"
        "VITE_SUPABASE_PUBLISHABLE_KEY=$anonKey"
        'VITE_API_BASE_URL=http://127.0.0.1:8000'
    ) | Set-Content -LiteralPath $frontendFile -Encoding utf8

    # Create one synthetic administrator account in local Auth only. Store its password locally.
    $credentialsFile = Join-Path $repoRoot '.local-test-credentials.txt'
    $email = 'kra-admin@example.test'
    $password = $null
    if (Test-Path -LiteralPath $credentialsFile) {
        $saved = Get-Content -LiteralPath $credentialsFile -Raw | ConvertFrom-Json
        if ($saved.email -eq $email -and $saved.password) { $password = [string]$saved.password }
    }
    if (-not $password) {
        $bytes = New-Object byte[] 36
        $rng = New-Object Security.Cryptography.RNGCryptoServiceProvider
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $password = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', 'A').Replace('/', 'B')
    }

    $headers = @{ apikey = $serviceKey; Authorization = "Bearer $serviceKey" }
    $users = Invoke-RestMethod -Method Get -Uri "$apiUrl/auth/v1/admin/users?page=1&per_page=1000" -Headers $headers
    $existing = @($users.users | Where-Object { $_.email -eq $email } | Select-Object -First 1)
    $userBody = @{
        email = $email
        password = $password
        email_confirm = $true
        app_metadata = @{ role = 'admin' }
    } | ConvertTo-Json -Depth 5
    if ($existing.Count -gt 0) {
        $userId = [string]$existing[0].id
        $null = Invoke-RestMethod -Method Put -Uri "$apiUrl/auth/v1/admin/users/$userId" -Headers $headers -ContentType 'application/json' -Body $userBody
    } else {
        $null = Invoke-RestMethod -Method Post -Uri "$apiUrl/auth/v1/admin/users" -Headers $headers -ContentType 'application/json' -Body $userBody
    }
    @{ email = $email; password = $password; note = 'Synthetic local Supabase QA account only.' } |
        ConvertTo-Json | Set-Content -LiteralPath $credentialsFile -Encoding utf8

    Write-Output 'Local Supabase is running. API/Auth and React settings target loopback and were written to ignored local files.'
    Write-Output 'Synthetic local administrator account is ready; credentials are stored in .local-test-credentials.txt.'
} finally {
    Pop-Location
}
