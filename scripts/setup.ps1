<#
  Openship setup for Windows (PowerShell) - mirrors scripts/setup.sh.

  Docker-first database (Postgres + pgvector runs in a container); Python and Node
  run locally. Run from the repo root:

      powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

  Prerequisites (install these first - the script does NOT download Docker):
    - Docker Desktop (installed and running)
  Python and Node are auto-installed via winget if missing.
#>

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path

function Info($m) { Write-Host "[setup] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[OK] $m"    -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m"     -ForegroundColor Yellow }
function Die($m)  { Write-Host "[x] $m"     -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "     Openship Setup (Windows)"          -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# -- Step 1: Python 3.11+ -----------------------------------------------------
Info "Step 1/6 - Python"
$PyExe = $null; $PyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue)          { $PyExe = "py"; $PyArgs = @("-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue)  { $PyExe = "python" }
elseif (Get-Command python3 -ErrorAction SilentlyContinue) { $PyExe = "python3" }

$pyOk = $false
if ($PyExe) {
    try {
        $ver = & $PyExe @PyArgs -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
        if ($ver -match '^3\.(1[1-9]|[2-9]\d)$') { $pyOk = $true }
    } catch { }
}
if (-not $pyOk) {
    Warn "Python 3.11+ not found."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info "Installing Python 3.12 via winget..."
        winget install -e --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
        # winget updates PATH in the registry but not this session - refresh it, then re-detect.
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        if (Get-Command py -ErrorAction SilentlyContinue)         { $PyExe = "py"; $PyArgs = @("-3") }
        elseif (Get-Command python -ErrorAction SilentlyContinue) { $PyExe = "python"; $PyArgs = @() }
        else { Die "Python was installed but isn't on PATH in this session. Close and reopen PowerShell, then re-run scripts\setup.cmd." }
    } else {
        Die "Python 3.11+ required. Install from https://www.python.org/downloads/ then re-run."
    }
}
Ok ("Python: " + (& $PyExe @PyArgs --version))

# -- Step 2: Database (Docker + pgvector) - Docker is a required prerequisite --
Info "Step 2/6 - Database (Docker + pgvector)"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Die "Docker is required. Install Docker Desktop, start it, then re-run.`n     Download: https://www.docker.com/products/docker-desktop/"
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { Die "Docker is installed but not running. Start Docker Desktop, then re-run." }

Info "Starting PostgreSQL + pgvector..."
docker compose -f "$Root\docker-compose.yml" up -d db
if ($LASTEXITCODE -ne 0) { Die "Failed to start the database container." }

Info "Waiting for the database to accept connections..."
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    docker compose -f "$Root\docker-compose.yml" exec -T db pg_isready -U openship -d openship *> $null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $ready) { Die "Database did not become ready in time." }
Ok "Database ready (Postgres 16 + pgvector) on localhost:5432."

# -- Steps 3 & 4: Secrets + .env ----------------------------------------------
$EnvPath = Join-Path $Root ".env"
if (Test-Path $EnvPath) {
    Info "Step 3/6 - .env already exists - leaving it untouched."
} else {
    Info "Step 3/6 - Generating secrets"
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $jwtBytes = New-Object byte[] 32; $rng.GetBytes($jwtBytes)
    $JwtSecret = ($jwtBytes | ForEach-Object { $_.ToString('x2') }) -join ''
    $keyBytes = New-Object byte[] 32; $rng.GetBytes($keyBytes)
    $LlmKey = [Convert]::ToBase64String($keyBytes).Replace('+', '-').Replace('/', '_')
    Ok "Secrets generated."

    Info "Step 4/6 - Writing .env"
    $envContent = @"
DATABASE_URL=postgresql+psycopg2://openship:openship@localhost:5432/openship

LLM_ENCRYPTION_KEY=$LlmKey

RUN_MIGRATIONS_ON_STARTUP=true

JWT_SECRET_KEY=$JwtSecret
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=2
JWT_REFRESH_TOKEN_EXPIRE_HOURS=7

SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=Openship
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_TIMEOUT_SECONDS=20
"@
    Set-Content -Path $EnvPath -Value $envContent
    Ok ".env written."
}

# -- Step 5: Python venv + deps, embedding model, Node + UI deps --------------
Info "Step 5/6 - Installing dependencies"
& $PyExe @PyArgs -m venv "$Root\.venv"
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
& $VenvPy -m pip install --upgrade pip -q
& $VenvPy -m pip install -r "$Root\requirements.txt" -r "$Root\requirements-dev.txt" -r "$Root\requirements-test.txt" -q
Ok "Python dependencies installed."

Info "Pre-downloading the local embedding model (one-time)..."
& $VenvPy "$Root\scripts\warm_embeddings.py"
if ($LASTEXITCODE -eq 0) { Ok "Embedding model ready." }
else { Warn "Could not pre-download the embedding model; it will download on first ingest." }

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Warn "Node.js not found (needed for the UI)."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info "Installing Node.js LTS via winget..."
        winget install -e --id OpenJS.NodeJS.LTS --silent --accept-source-agreements --accept-package-agreements
        # Refresh PATH so npm is usable in this session (winget only updates the registry).
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            Die "Node.js was installed but isn't on PATH in this session. Close and reopen PowerShell, then re-run scripts\setup.cmd."
        }
    } else {
        Die "Node.js is required for the UI. Install from https://nodejs.org and re-run."
    }
}
Push-Location "$Root\ui"; npm install --silent; Pop-Location
Ok "Node dependencies installed."

# -- Step 6: Migrations (creates tables + enables pgvector) -------------------
Info "Step 6/6 - Running database migrations..."
Push-Location $Root
& (Join-Path $Root ".venv\Scripts\alembic.exe") upgrade head
Pop-Location
Ok "Migrations applied."

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "        Setup complete!"                -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Run:  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1"
Write-Host ""
