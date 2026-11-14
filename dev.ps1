<#
.SYNOPSIS
    Run EduAgent Hub locally: database (Docker), backend (FastAPI :8001), frontend (Vite :5173).

.EXAMPLE
    .\dev.ps1            # start everything (installs deps on first run)
    .\dev.ps1 -Setup     # force reinstall deps + re-seed demo data
    .\dev.ps1 -NoWeb     # only database + backend
    .\dev.ps1 -Stop      # stop the database container
#>
[CmdletBinding()]
param(
    [switch]$Setup,
    [switch]$NoWeb,
    [switch]$NoBackend,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Compose = Join-Path $Root 'infra/docker-compose.yml'
$Backend = Join-Path $Root 'backend'
$Web = Join-Path $Root 'web'

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Invoke-Checked {
    param([string]$Dir, [scriptblock]$Block)
    Push-Location $Dir
    try {
        & $Block
        if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE) in $Dir" }
    } finally { Pop-Location }
}

function Assert-Command($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "'$name' not found. $hint" }
}

if ($Stop) {
    Step 'Stopping database'
    docker compose -f $Compose down
    exit $LASTEXITCODE
}

Assert-Command docker 'Install Docker Desktop.'
Assert-Command uv 'Install uv: https://docs.astral.sh/uv/'
Assert-Command npm 'Install Node.js.'

# .env
$envFile = Join-Path $Root '.env'
if (-not (Test-Path $envFile)) {
    Step 'Creating .env from .env.example'
    Copy-Item (Join-Path $Root '.env.example') $envFile
}

# Docker daemon
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker is not running. Start Docker Desktop and try again.' }

# Database
Step 'Starting Postgres + pgvector (127.0.0.1:5433)'
docker compose -f $Compose up -d --wait
if ($LASTEXITCODE -ne 0) { throw 'Database failed to start.' }

# Pick the shell used for the new windows (pwsh if available, else Windows PowerShell)
$Shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }

function Start-Window($title, $dir, $command) {
    $cmd = "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location '$dir'; $command"
    Start-Process $Shell -ArgumentList '-NoExit', '-Command', $cmd | Out-Null
}

if (-not $NoBackend) {
    $firstRun = -not (Test-Path (Join-Path $Backend '.venv'))
    if ($Setup -or $firstRun) {
        Step 'Installing backend dependencies (uv sync)'
        Invoke-Checked $Backend { uv sync }
    }

    Step 'Applying migrations'
    Invoke-Checked $Backend { uv run alembic upgrade head }

    if ($Setup -or $firstRun) {
        Step 'Seeding demo data'
        Invoke-Checked $Backend { uv run python -m scripts.seed_demo }
    }

    Step 'Starting backend in a new window -> http://127.0.0.1:8001'
    Start-Window 'EduAgent backend' $Backend 'uv run uvicorn app.main:app --reload --port 8001'
}

if (-not $NoWeb) {
    if ($Setup -or -not (Test-Path (Join-Path $Web 'node_modules'))) {
        Step 'Installing frontend dependencies (npm install)'
        Invoke-Checked $Web { npm install }
    }

    Step 'Starting frontend in a new window -> http://127.0.0.1:5173'
    Start-Window 'EduAgent web' $Web 'npm run dev'
}

Write-Host ''
Write-Host 'Ready. Open http://127.0.0.1:5173' -ForegroundColor Green
Write-Host 'Demo accounts (password Demo123!): teacher@ / student@ / parent@ / admin@demo.edu.vn'
Write-Host 'Stop: close the backend/web windows, then run .\dev.ps1 -Stop'
