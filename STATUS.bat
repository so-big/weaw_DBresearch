@echo off
@chcp 65001 >nul
title DBresearch - Status
color 0E

:: Read PORT from .env or default to 8120
set APP_PORT=8120
if exist .env (
    for /f "tokens=1,2 delims==" %%a in (.env) do (
        if "%%a"=="PORT" set APP_PORT=%%b
    )
)

echo ======================================================================
echo                  DBresearch System Status
echo ======================================================================
echo.

wsl bash -c "docker ps --filter name=dbresearch --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

echo.
echo ----------------------------------------------------------------------
echo  API Health Check:
echo ----------------------------------------------------------------------
curl.exe -s http://127.0.0.1:%APP_PORT%/health
echo.
echo.
echo ======================================================================
echo  - Web URL:   http://localhost:%APP_PORT%
echo  - API Docs:  http://localhost:%APP_PORT%/api/docs
echo ======================================================================
echo.
pause
