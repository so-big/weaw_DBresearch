@echo off
@chcp 65001 >nul
title Stop Development Sandbox Stack
color 0C

echo ======================================================================
echo              Stopping Development Sandbox Stack...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose -f docker-compose.dev.yml down"

echo.
echo ======================================================================
echo  [SUCCESS] Development Sandbox stopped.
echo ======================================================================
echo.
pause
