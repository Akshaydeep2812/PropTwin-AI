# Starts PropTwin AI on this computer with one command: .\start.ps1
#
# Safe to run again at any time. It creates .env only if there is none, keeps your data, and skips steps already done.
# The first run downloads PyTorch and takes several minutes. Local use only: see docs/DEPLOYMENT.md for production.

param([switch]$NoBrowser)

# Not "Stop": Windows PowerShell would treat Docker's ordinary progress output on stderr as a fatal error.
# Each native command's exit code is checked instead.
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

function New-Secret($bytes) {
    $buffer = New-Object byte[] $bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buffer)
    $rng.Dispose()
    # Hex, because these values are placed inside a database URL.
    return ([System.BitConverter]::ToString($buffer) -replace "-", "").ToLower()
}

Write-Step "Checking Docker"
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not running. Start Docker Desktop, wait until it is ready, then run this again." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Step "Creating .env with new random secrets"
    $databasePassword = New-Secret 18
    $content = Get-Content ".env.example" -Raw
    $content = $content.Replace("replace-with-a-local-root-password", (New-Secret 18))
    $content = $content.Replace("replace-with-a-local-password", $databasePassword)
    $content = $content.Replace("replace-with-a-long-random-local-secret", (New-Secret 32))
    $content = $content -replace "(?m)^DEMO_PASSWORD=\s*$", "DEMO_PASSWORD=$(New-Secret 12)"
    # Without a byte order mark, which Docker Compose would read as part of the first variable's name.
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot ".env"), $content, (New-Object System.Text.UTF8Encoding($false)))
}

Write-Step "Building and starting the services (the first run takes several minutes)"
& docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "The services could not start. See the messages above." -ForegroundColor Red; exit 1 }

Write-Step "Waiting for the API"
$ready = $false
foreach ($attempt in 1..60) {
    try {
        Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/live" -TimeoutSec 3 -ErrorAction Stop | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 3
    }
}
if (-not $ready) {
    Write-Host "The API did not become ready in 3 minutes. Run: docker compose logs backend" -ForegroundColor Red
    exit 1
}

function Invoke-Backend {
    & docker compose exec -T backend @args
    if ($LASTEXITCODE -ne 0) {
        Write-Host "This step failed: $args" -ForegroundColor Red
        exit 1
    }
}

Write-Step "Loading demo accounts, listings and market data"
Invoke-Backend python /app/database/seed/seed_demo.py

Write-Step "Preparing the valuation model"
& docker compose exec -T backend python -m app.cli ensure-model --admin-email demo.admin@proptwin.example 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "No trained model yet, so training one. This takes about a minute."
    Invoke-Backend python /app/ml/scripts/train.py
    Invoke-Backend python -m app.cli ensure-model --admin-email demo.admin@proptwin.example
}

Write-Step "Filling the demo accounts with real estimates and scenarios"
Invoke-Backend python /app/database/seed/seed_demo.py

Write-Host "`nPropTwin AI is ready." -ForegroundColor Green
Write-Host "  Open:      http://localhost:5173"
Write-Host "  Try it:    choose an 'Explore as' button. No password is needed."
Write-Host "  API docs:  http://localhost:8000/docs"
Write-Host "  Stop it:   docker compose stop"
if (-not $NoBrowser) { Start-Process "http://localhost:5173" }
