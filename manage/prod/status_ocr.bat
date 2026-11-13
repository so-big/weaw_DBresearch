@echo off
@chcp 65001 >nul
title Production OCR Worker Status
color 0E

echo ======================================================================
echo               Production OCR Worker Container Status
echo ======================================================================
echo.

wsl bash -c "docker ps --filter name=dbresearch-ocr --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

echo.
echo ----------------------------------------------------------------------
echo  Recent OCR Logs (Last 20 lines):
echo ----------------------------------------------------------------------
wsl bash -c "docker logs dbresearch-ocr --tail 20" 2>nul

echo.
echo ======================================================================
pause
