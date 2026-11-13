@chcp 65001 >nul
@echo off
title Stop Production OCR Worker
color 0C

echo ======================================================================
echo           Stopping DBresearch Production OCR Worker...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose stop ocr"
set ERR=%ERRORLEVEL%

echo.
if %ERR% EQU 0 (
    echo ======================================================================
    echo  [SUCCESS] Production OCR Worker stopped.
    echo ======================================================================
) else (
    echo ======================================================================
    echo  [ERROR] เกิดข้อผิดพลาดในการหยุด OCR Worker (Error Code: %ERR%)
    echo ======================================================================
)

echo.
echo กดปุ่มใดๆ เพื่อกลับสู่เมนูหลัก...
pause >nul
exit /b %ERR%