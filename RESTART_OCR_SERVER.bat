@echo off
@chcp 65001 >nul
title DBresearch - Restart OCR Server
color 0B

echo ======================================================================
echo                 Restarting OCR Server...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose restart worker"

echo.
echo ======================================================================
echo  [SUCCESS] OCR Server restarted!
echo ======================================================================
echo.
pause
