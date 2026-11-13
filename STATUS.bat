@echo off
@chcp 65001 >nul
title DBresearch - Status
color 0E

set APP_PORT=8120
if exist setting.txt (
    for /f "tokens=1,2 delims==" %%a in (setting.txt) do (
        set "key=%%a"
        set "val=%%b"
        call set "key=%%key: =%%"
        call set "val=%%val: =%%"
        if /i "%%key%%"=="port" set APP_PORT=%%val%%
    )
)

echo ======================================================================
echo                  DBresearch System Status
echo ======================================================================
echo.

wsl bash -c "docker ps --filter name=dbresearch --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -v 'healthy'"
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
