# Start Script for Singing Voice Conversion Application
param(
    [switch]$Share
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Singing Voice Conversion Web Application (RVC)         " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check frontend build
$DistPath = Join-Path $ScriptDir "frontend\dist\index.html"
if (-not (Test-Path $DistPath)) {
    Write-Host "[1/2] Building frontend UI..." -ForegroundColor Yellow
    Set-Location (Join-Path $ScriptDir "frontend")
    npm run build
    Set-Location $ScriptDir
} else {
    Write-Host "[1/2] Frontend build verified (frontend/dist/)" -ForegroundColor Green
}

# 2. Check for public tunnel if requested
if ($Share) {
    $Cloudflared = "E:\LAB TW\Help\cloudflared.exe"
    if (Test-Path $Cloudflared) {
        Write-Host "Starting Cloudflare HTTPS tunnel in background..." -ForegroundColor Magenta
        Start-Process -FilePath $Cloudflared -ArgumentList "tunnel", "--url", "http://localhost:8000"
    }
}

# 3. Launch Backend
$CondaPy = "E:\LAB TW\Help\conda_envs\rvc\python.exe"
$PyCmd = if (Test-Path $CondaPy) { $CondaPy } else { "python" }

# Check websockets dependency
& $PyCmd -c "import websockets" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[Setup] Installing required websocket dependencies..." -ForegroundColor Yellow
    & $PyCmd -m pip install websockets "uvicorn[standard]"
}

Write-Host "[2/2] Launching FastAPI Backend on http://localhost:8000 ..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor Gray
& $PyCmd backend/main.py

