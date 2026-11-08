<#
.SYNOPSIS
    Start the whole EduAgent Hub stack locally with one command.

.DESCRIPTION
    1. Starts Dify (docker compose in $DifyDir) and waits until it answers on :8080
    2. Starts Postgres (infra/docker-compose.yml) and waits until it is healthy
    3. Runs Alembic migrations (and the demo seed with -Seed)
    4. Opens backend (:8001) and web (:5173) in two new terminal windows
    5. Waits for /api/health and opens the browser

.EXAMPLE
    .\dev.ps1               # normal start
    .\dev.ps1 -Seed         # also (re)create demo data; idempotent
    .\dev.ps1 -NoDify       # skip Dify (tests, UI work)
    .\dev.ps1 -Stop         # stop Dify and Postgres containers
#>
param(
    [switch]$Seed,
    [switch]$NoDify,
    [switch]$NoBrowser,
    [switch]$Stop,
    [string]$DifyDir = $(if ($env:DIFY_DIR) { $env:DIFY_DIR } else { 'C:\project\dify' })
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Web = Join-Path $Root 'web'
$Compose = Join-Path $Root 'infra\docker-compose.yml'
$DifyDocker = Join-Path $DifyDir 'docker'
$Shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "x $msg" -ForegroundColor Red; exit 1 }

function Wait-Http($url, $seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 | Out-Null
            return $true
        } catch {
            # Not up yet, or nginx answering 502 while the Dify api container boots.
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

function Invoke-Checked([string]$what, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { Fail "$what failed (exit $LASTEXITCODE)" }
}

# ---- stop -------------------------------------------------------------------
if ($Stop) {
    Step 'Stopping Postgres'
    docker compose -f $Compose stop
    if (Test-Path $DifyDocker) {
        Step 'Stopping Dify'
        Push-Location $DifyDocker; docker compose stop; Pop-Location
    }
    Write-Host 'Done. Close the backend/web windows yourself (Ctrl+C).' -ForegroundColor Green
    exit 0
}

# ---- preflight --------------------------------------------------------------
Step 'Checking tools'
foreach ($tool in 'docker', 'uv', 'npm') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Fail "'$tool' is not on PATH" }
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker is not running. Start Docker Desktop first.' }
if (-not (Test-Path (Join-Path $Root '.env'))) {
    Fail '.env not found. Copy .env.example to .env and fill DIFY_* and MCP_TOKEN (see README).'
}

# ---- Dify -------------------------------------------------------------------
if (-not $NoDify) {
    if (-not (Test-Path $DifyDocker)) {
        Fail "Dify not found at $DifyDir. Pass -DifyDir <path>, set DIFY_DIR, or use -NoDify."
    }
    Step "Starting Dify ($DifyDocker)"
    Push-Location $DifyDocker
    try { Invoke-Checked 'docker compose up (Dify)' { docker compose up -d } } finally { Pop-Location }

    Step 'Waiting for Dify on http://127.0.0.1:8080 (up to 3 min)'
    if (-not (Wait-Http 'http://127.0.0.1:8080/console/api/ping' 180)) {
        Fail 'Dify did not come up. Check: docker compose logs api (in the Dify docker folder).'
    }
}

# ---- Postgres ---------------------------------------------------------------
Step 'Starting Postgres (port 5433)'
Invoke-Checked 'docker compose up (Postgres)' { docker compose -f $Compose up -d --wait }

# ---- backend prep -----------------------------------------------------------
Push-Location $Backend
try {
    Step 'Syncing Python deps and running migrations'
    Invoke-Checked 'uv sync' { uv sync --quiet }
    Invoke-Checked 'alembic upgrade' { uv run alembic upgrade head }
    if ($Seed) {
        Step 'Seeding demo data'
        Invoke-Checked 'seed_demo' { uv run python -m scripts.seed_demo }
    }
} finally { Pop-Location }

# ---- web prep ---------------------------------------------------------------
if (-not (Test-Path (Join-Path $Web 'node_modules'))) {
    Step 'Installing web deps (first run)'
    Push-Location $Web
    try { Invoke-Checked 'npm install' { npm install } } finally { Pop-Location }
}

# ---- launch servers ---------------------------------------------------------
Step 'Opening backend window (http://127.0.0.1:8001)'
Start-Process $Shell -WorkingDirectory $Backend -ArgumentList @(
    '-NoExit', '-Command',
    "`$host.UI.RawUI.WindowTitle='EduAgent backend'; uv run uvicorn app.main:app --reload --port 8001"
)

Step 'Opening web window (http://127.0.0.1:5173)'
Start-Process $Shell -WorkingDirectory $Web -ArgumentList @(
    '-NoExit', '-Command',
    "`$host.UI.RawUI.WindowTitle='EduAgent web'; npm run dev"
)

Step 'Waiting for backend health'
if (Wait-Http 'http://127.0.0.1:8001/api/health' 60) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8001/api/health' -TimeoutSec 5
        Write-Host ($health | ConvertTo-Json -Compress)
    } catch { }
} else {
    Write-Host '! Backend did not answer in 60 s; check the backend window.' -ForegroundColor Yellow
}

if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5173' }

Write-Host ''
Write-Host 'EduAgent Hub is running:' -ForegroundColor Green
Write-Host '  Web      http://127.0.0.1:5173   (demo password: Demo123!)'
Write-Host '  Backend  http://127.0.0.1:8001'
if (-not $NoDify) { Write-Host '  Dify     http://127.0.0.1:8080' }
Write-Host 'Stop: Ctrl+C in the two windows, then .\dev.ps1 -Stop'
