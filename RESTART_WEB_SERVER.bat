@echo off
@chcp 65001 >nul
title DBresearch - Restart Web Server
color 0A

echo ======================================================================
echo                 Restarting Web Server...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose restart api"

echo.
echo ======================================================================
echo  [SUCCESS] Web Server restarted!
echo ======================================================================
echo.
pause
