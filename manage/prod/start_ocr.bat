@echo off
@chcp 65001 >nul
title Start Production OCR Worker
color 0B

echo ======================================================================
echo           Starting DBresearch Production OCR Worker...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose up -d ocr"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo  [SUCCESS] Production OCR Worker started successfully!
    echo  - Container: dbresearch-ocr
    echo  - Backend:   MySQL Queue (10.27.50.43:3307)
    echo ======================================================================
) else (
    echo.
    echo [ERROR] Failed to start OCR Worker.
)

echo.
pause
