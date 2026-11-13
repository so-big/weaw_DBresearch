@chcp 65001 >nul
@echo off
title Start Production OCR Worker
color 0B

echo ======================================================================
echo           Starting DBresearch Production OCR Worker...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose up -d ocr"
set ERR=%ERRORLEVEL%

echo.
if %ERR% EQU 0 (
    echo ======================================================================
    echo  [SUCCESS] Production OCR Worker started successfully!
    echo  - Container: dbresearch-ocr
    echo  - Backend:   MySQL Queue (10.27.50.43:3307)
    echo ======================================================================
) else (
    color 0C
    echo ======================================================================
    echo  [ERROR] ไม่สามารถเริ่มทำงาน OCR Worker ได้ (Error Code: %ERR%)
    echo  - กรุณาตรวจสอบว่า Docker Desktop / WSL กำลังทำงานอยู่หรือไม่
    echo ======================================================================
)

echo.
echo กดปุ่มใดๆ เพื่อกลับสู่เมนูหลัก...
pause >nul
exit /b %ERR%