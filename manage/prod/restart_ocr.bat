@chcp 65001 >nul
@echo off
title Restart Production OCR Worker
color 0B

echo ======================================================================
echo           Restarting DBresearch Production OCR Worker...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose restart ocr"
set ERR=%ERRORLEVEL%

echo.
if %ERR% EQU 0 (
    echo ======================================================================
    echo  [SUCCESS] Production OCR Worker restarted.
    echo ======================================================================
) else (
    color 0C
    echo ======================================================================
    echo  [ERROR] เกิดข้อผิดพลาดในการรีสตาร์ท OCR Worker (Error Code: %ERR%)
    echo ======================================================================
)

echo.
echo กดปุ่มใดๆ เพื่อกลับสู่เมนูหลัก...
pause >nul
exit /b %ERR%