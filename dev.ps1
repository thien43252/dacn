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

function Test-Port($port) {
    [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Start-Window($title, $dir, $command) {
    $cmd = "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location '$dir'; $command"
    Start-Process $Shell -ArgumentList '-NoExit', '-Command', $cmd | Out-Null
}

function Invoke-Psql($db, $sql) {
    $out = docker compose -f $Compose exec -T postgres psql -U eduagent -d $db -tAc $sql 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($out | Out-String).Trim()
}

# Pick a database whose migration history matches this checkout. Branches share one Postgres container; if another
# branch migrated the default database past what this code knows (alembic: "Can't locate revision"), use a separate
# database for this branch instead of touching the other branch's data.
function Select-Database {
    $known = Get-ChildItem (Join-Path $Backend 'migrations/versions') -Filter *.py |
        Select-String -Pattern '^revision[^=]*=\s*"([^"]+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value }

    $db = 'eduagent'
    $current = Invoke-Psql $db 'SELECT version_num FROM alembic_version'
    if ($current -and ($known -notcontains $current)) {
        $branch = (git -C $Root rev-parse --abbrev-ref HEAD 2>$null) -replace '[^A-Za-z0-9]', '_'
        if (-not $branch) { $branch = 'local' }
        $db = "eduagent_$($branch.ToLower())"
        Write-Host "    Database 'eduagent' is at revision $current, unknown to this branch -> using '$db'" -ForegroundColor Yellow
        $exists = Invoke-Psql 'eduagent' "SELECT 1 FROM pg_database WHERE datname = '$db'"
        if ($exists -ne '1') {
            Step "Creating database $db"
            docker compose -f $Compose exec -T postgres psql -U eduagent -d eduagent -c "CREATE DATABASE $db" | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Could not create database $db" }
        }
        $current = Invoke-Psql $db 'SELECT version_num FROM alembic_version'
    }
    # Child processes (alembic, seed, the backend window) inherit this; it overrides DATABASE_URL in .env.
    $env:DATABASE_URL = "postgresql+asyncpg://eduagent:eduagent@127.0.0.1:5433/$db"
    return [pscustomobject]@{ Name = $db; Fresh = -not $current }
}

if (-not $NoBackend) {
    $firstRun = -not (Test-Path (Join-Path $Backend '.venv'))
    if ($Setup -or $firstRun) {
        Step 'Installing backend dependencies (uv sync)'
        Invoke-Checked $Backend { uv sync }
    }

    $database = Select-Database

    Step "Applying migrations ($($database.Name))"
    Invoke-Checked $Backend { uv run alembic upgrade head }

    # The seed is idempotent: on an existing database it only adds what a newer demo needs (feature 003 accounts,
    # subject teacher, demo group, approval modes), so it runs on every start.
    if ($Setup -or $firstRun -or $database.Fresh) {
        Step 'Seeding demo data'
    } else {
        Step 'Ensuring demo data is up to date'
    }
    Invoke-Checked $Backend { uv run python -m scripts.seed_demo --ensure }

    if (Test-Port 8001) {
        Write-Host '    Port 8001 already in use - backend is probably running, not starting another.' -ForegroundColor Yellow
    } else {
        Step 'Starting backend in a new window -> http://127.0.0.1:8001'
        Start-Window 'EduAgent backend' $Backend 'uv run uvicorn app.main:app --reload --port 8001'
    }
}

if (-not $NoWeb) {
    if ($Setup -or -not (Test-Path (Join-Path $Web 'node_modules'))) {
        Step 'Installing frontend dependencies (npm install)'
        Invoke-Checked $Web { npm install }
    }

    if (Test-Port 5173) {
        Write-Host '    Port 5173 already in use - frontend is probably running, not starting another.' -ForegroundColor Yellow
    } else {
        Step 'Starting frontend in a new window -> http://127.0.0.1:5173'
        Start-Window 'EduAgent web' $Web 'npm run dev'
    }
}

Write-Host ''
Write-Host 'Ready. Open http://127.0.0.1:5173' -ForegroundColor Green
Write-Host 'Demo accounts (password Demo123!): teacher@ / student@ / parent@ / admin@demo.edu.vn'
Write-Host '  plus toan@ (maths teacher), student2@ / parent2@demo.edu.vn (second family, demo group)'
Write-Host 'Stop: close the backend/web windows, then run .\dev.ps1 -Stop'
