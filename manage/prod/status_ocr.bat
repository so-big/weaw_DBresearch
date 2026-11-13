@echo off
@chcp 65001 >nul
title Production OCR Worker Status
color 0E

echo ======================================================================
echo               Production OCR Worker Container Status
echo ======================================================================
echo.

wsl bash -c "docker ps --filter name=dbresearch-ocr --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
set ERR=%ERRORLEVEL%

echo.
echo ----------------------------------------------------------------------
echo  Recent OCR Logs (Last 20 lines):
echo ----------------------------------------------------------------------
wsl bash -c "docker logs dbresearch-ocr --tail 20" 2>nul

echo.
echo ======================================================================
if %ERR% NEQ 0 (
    color 0C
    echo  [NOTE] เกิดข้อผิดพลาดในการดึงข้อมูลจาก Docker (Error Code: %ERR%)
    echo ======================================================================
)

echo.
echo กดปุ่มใดๆ เพื่อกลับสู่เมนูหลัก...
pause >nul
exit /b %ERR%