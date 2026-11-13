@echo off
@chcp 65001 >nul
title DBresearch - Start All Services
color 0A

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
echo       Starting DBresearch (OCR Server first, then Web Server)...
echo ======================================================================
echo.

echo [1/2] Starting OCR Server...
wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose up -d db worker"

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to start OCR Server
    pause
    exit /b %ERRORLEVEL%
)
echo [OK] OCR Server is running!
echo.

echo [2/2] Starting Web Server...
wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose up -d api"

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to start Web Server
    pause
    exit /b %ERRORLEVEL%
)
echo [OK] Web Server is running!
echo.

echo ======================================================================
echo  [SUCCESS] All DBresearch services are running!
echo ======================================================================
echo  - Web URL:    http://localhost:%APP_PORT%
echo  - API Docs:   http://localhost:%APP_PORT%/api/docs
echo  - Config:     setting.txt
echo ======================================================================
echo.
echo Opening browser...
start http://localhost:%APP_PORT%
echo.
pause
