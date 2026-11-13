@echo off
@chcp 65001 >nul
title DBresearch - Start OCR Server
color 0B

echo ======================================================================
echo          Starting OCR Server (Tesseract Thai/Eng Worker)...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose up -d db worker"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to start OCR Server. Please check Docker.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ======================================================================
echo  [SUCCESS] OCR Server started successfully!
echo ======================================================================
echo  - Container: dbresearch-ocr (Worker)
echo  - Status: Running in background
echo.
echo  Next step:
echo  Run '2_START_WEB_SERVER.bat' to launch the web system.
echo ======================================================================
echo.
pause
