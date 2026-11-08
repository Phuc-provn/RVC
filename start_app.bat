@echo off
title Singing Voice Conversion
cd /d "%~dp0"
echo ========================================================
echo   Singing Voice Conversion Web Application (RVC)
echo ========================================================
if not exist "frontend\dist\index.html" (
    echo [1/2] Building frontend UI...
    cd frontend
    call npm run build
    cd ..
)
REM Determine python executable
set "PY_CMD=python"
if exist "E:\LAB TW\Help\conda_envs\rvc\python.exe" (
    set "PY_CMD=E:\LAB TW\Help\conda_envs\rvc\python.exe"
)

REM Check and auto-install websockets if missing
"%PY_CMD%" -c "import websockets" 2>nul
if errorlevel 1 (
    echo [Setup] Installing required websocket dependencies...
    "%PY_CMD%" -m pip install websockets "uvicorn[standard]"
)

echo [2/2] Starting FastAPI Backend on http://localhost:8000 ...
"%PY_CMD%" backend\main.py
pause

