@echo off
@chcp 65001 >nul
title DBresearch - Stop Web Server
color 0C

echo ======================================================================
echo                  Stopping Web Server...
echo ======================================================================
echo.

wsl bash -c "docker stop dbresearch-web"

echo.
echo ======================================================================
echo  [SUCCESS] Web Server stopped.
echo ======================================================================
echo.
pause
