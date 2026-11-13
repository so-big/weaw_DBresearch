@echo off
@chcp 65001 >nul
title DBresearch - Start Web Server
color 0A

:: Read PORT from .env or default to 8120
set APP_PORT=8120
if exist .env (
    for /f "tokens=1,2 delims==" %%a in (.env) do (
        if "%%a"=="PORT" set APP_PORT=%%b
    )
)

echo ======================================================================
echo                  Starting Web Server (FastAPI + Svelte)...
echo ======================================================================
echo.

wsl bash -c "docker ps --filter name=dbresearch-ocr --filter status=running -q" > temp_ocr_check.txt
set /p OCR_RUNNING=<temp_ocr_check.txt
del temp_ocr_check.txt 2>nul

if "%OCR_RUNNING%"=="" (
    color 0E
    echo ----------------------------------------------------------------------
    echo  [NOTICE] OCR Server is NOT running!
    echo  - Web system will run normally.
    echo  - Uploaded files will not be auto-OCRed until you start OCR Server
    echo    using '1_START_OCR_SERVER.bat'.
    echo ----------------------------------------------------------------------
    echo.
) else (
    echo [OK] OCR Server is active. OCR auto-processing is ENABLED.
    echo.
)

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose up -d db api"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to start Web Server. Please check Docker.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ======================================================================
echo  [SUCCESS] Web Server started successfully!
echo ======================================================================
echo  - Web URL:    http://localhost:%APP_PORT%
echo  - API Docs:   http://localhost:%APP_PORT%/api/docs
echo.
echo  Default Login (from root.txt):
echo  - See root.txt in root folder (Line 1: user, Line 2: password)
echo ======================================================================
echo.
echo Opening browser...
start http://localhost:%APP_PORT%
echo.
pause
