@echo off
@chcp 65001 >nul
title DBresearch - Stop OCR Server
color 0C

echo ======================================================================
echo                  Stopping OCR Server (Worker)...
echo ======================================================================
echo.

wsl bash -c "docker stop dbresearch-ocr"

echo.
echo ======================================================================
echo  [SUCCESS] OCR Server stopped.
echo ======================================================================
echo  - Container dbresearch-ocr is now stopped (saving CPU/RAM).
echo  - Web Server is still running.
echo ======================================================================
echo.
pause
