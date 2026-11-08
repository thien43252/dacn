<#
.SYNOPSIS
    Start the whole EduAgent Hub stack locally with one command.

.DESCRIPTION
    1. Starts Dify (docker compose in $DifyDir) and waits until it answers on :8080
    2. Starts Postgres (infra/docker-compose.yml) and waits until it is healthy
    3. Runs Alembic migrations (and the demo seed with -Seed)
    4. Runs backend (:8001) and web (:5173) together in THIS terminal; Ctrl+C stops both
    5. Waits for /api/health and opens the browser

    Web runs as the Vite dev server (hot reload) by default. With -Build it is built first
    (tsc + vite build) and served by `vite preview` on the same port, with the same /api proxy.

.EXAMPLE
    .\dev.ps1               # normal start (web with hot reload)
    .\dev.ps1 -Build        # build web first, then serve the built bundle
    .\dev.ps1 -Seed         # also (re)create demo data; idempotent
    .\dev.ps1 -NoDify       # skip Dify (tests, UI work)
    .\dev.ps1 -Stop         # stop Dify and Postgres containers
#>
param(
    [switch]$Build,
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
$ViteJs = Join-Path $Web 'node_modules\vite\bin\vite.js'

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
    Write-Host 'Done. (Backend and web stop with Ctrl+C in the terminal running dev.ps1.)' -ForegroundColor Green
    exit 0
}

# ---- preflight --------------------------------------------------------------
Step 'Checking tools'
foreach ($tool in 'docker', 'uv', 'npm', 'node') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Fail "'$tool' is not on PATH" }
}
foreach ($port in 8001, 5173) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        Fail "Port $port is already in use (an old backend/web still running?). Stop it and retry."
    }
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
if ($Build) {
    Step 'Building web (tsc + vite build)'
    Push-Location $Web
    try { Invoke-Checked 'npm run build' { npm run build } } finally { Pop-Location }
}

# ---- run backend + web in this terminal -------------------------------------
# Both share this console: their logs interleave here and Ctrl+C reaches both.
# Vite is started through node directly (not npm.cmd) so Ctrl+C does not trigger
# cmd's "Terminate batch job (Y/N)?" prompt.
$procs = @()
try {
    Step 'Starting backend (http://127.0.0.1:8001)'
    $procs += Start-Process -FilePath (Get-Command uv).Source -WorkingDirectory $Backend -NoNewWindow -PassThru `
        -ArgumentList 'run', 'uvicorn', 'app.main:app', '--reload', '--port', '8001'

    $webMode = if ($Build) { 'preview' } else { 'dev' }
    Step "Starting web: vite $webMode (http://127.0.0.1:5173)"
    $viteArgs = @("`"$ViteJs`"")
    if ($Build) { $viteArgs += 'preview' }
    $viteArgs += '--host', '127.0.0.1', '--port', '5173', '--strictPort'
    $procs += Start-Process -FilePath (Get-Command node).Source -WorkingDirectory $Web -NoNewWindow -PassThru `
        -ArgumentList $viteArgs

    Step 'Waiting for backend health'
    if (Wait-Http 'http://127.0.0.1:8001/api/health' 60) {
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:8001/api/health' -TimeoutSec 5
            Write-Host ($health | ConvertTo-Json -Compress)
        } catch { }
    } else {
        Write-Host '! Backend did not answer in 60 s; see the log above.' -ForegroundColor Yellow
    }

    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5173' }

    Write-Host ''
    Write-Host 'EduAgent Hub is running:' -ForegroundColor Green
    Write-Host "  Web      http://127.0.0.1:5173   ($webMode; demo password: Demo123!)"
    Write-Host '  Backend  http://127.0.0.1:8001'
    if (-not $NoDify) { Write-Host '  Dify     http://127.0.0.1:8080' }
    Write-Host 'Ctrl+C stops backend and web. Containers keep running; .\dev.ps1 -Stop stops them.'
    Write-Host ''

    # If either server dies, stop the other one too.
    while (-not ($procs | Where-Object HasExited)) { Start-Sleep -Seconds 1 }
    $dead = $procs | Where-Object HasExited | Select-Object -First 1
    Write-Host "! $($dead.ProcessName) exited (code $($dead.ExitCode)); stopping the rest." -ForegroundColor Yellow
} finally {
    # Runs on normal exit and on Ctrl+C: kill whole trees (uvicorn --reload spawns children).
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) { taskkill /T /F /PID $p.Id *> $null }
    }
}
