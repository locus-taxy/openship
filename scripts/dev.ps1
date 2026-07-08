<#
  Openship dev launcher for Windows (PowerShell) — mirrors `make dev`.

  Starts the database (Docker), then opens the API and the UI in two new
  PowerShell windows. Run from the repo root:

      powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#>

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path

Write-Host "Ensuring the database is up..." -ForegroundColor Cyan
docker compose -f "$Root\docker-compose.yml" up -d db
if ($LASTEXITCODE -ne 0) {
    Write-Host "[x] Could not start the database. Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

$uvicorn = Join-Path $Root ".venv\Scripts\uvicorn.exe"

Write-Host "Opening API window (http://localhost:3005)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$Root'; Write-Host '=== Openship API ==='; & '$uvicorn' main:app --reload --host 0.0.0.0 --port 3005"
)

Write-Host "Opening UI window (http://localhost:5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$Root\ui'; Write-Host '=== Openship UI ==='; npm run dev"
)

Write-Host ""
Write-Host "Done - API on http://localhost:3005, UI on http://localhost:5173." -ForegroundColor Green
Write-Host "Close the two windows to stop. Run scripts\dev.ps1 again to restart."
