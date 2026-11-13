@echo off
@chcp 65001 >nul
title DBresearch - Stop All Services
color 0C

echo ======================================================================
echo                  Stopping all DBresearch services...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose down"

echo.
echo ======================================================================
echo  [SUCCESS] All services stopped (Web, OCR, Database).
echo ======================================================================
echo.
pause
