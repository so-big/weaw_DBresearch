@echo off
@chcp 65001 >nul
title Start Development Sandbox Stack
color 0A

:: Read PORT from setting.txt or default 8120
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
echo       Starting Development Sandbox Stack (Web + DB + Worker)...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose -f docker-compose.dev.yml up -d"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo  [SUCCESS] Development Sandbox is running!
    echo  - Web URL:    http://localhost:%APP_PORT%
    echo  - API Docs:   http://localhost:%APP_PORT%/api/docs
    echo ======================================================================
    start http://localhost:%APP_PORT%
) else (
    echo.
    echo [ERROR] Failed to start Dev Stack.
)

echo.
pause
