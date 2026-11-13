@echo off
@chcp 65001 >nul
title Create Dev Admin User
color 0B

echo ======================================================================
echo                  Create Dev Admin User
echo ======================================================================
echo.

set /p USERNAME="Enter Username: "
set /p DISPLAY_NAME="Enter Display Name: "
set /p EMAIL="Enter Email: "
set /p PASSWORD="Enter Password (at least 10 characters): "

echo.
echo Creating user in Dev DB...
wsl bash -c "cd /mnt/e/wear_DBresearch && DBR_PASSWORD='%PASSWORD%' docker compose -f docker-compose.dev.yml exec -e DBR_PASSWORD api python -m dbresearch.cli create-admin --username '%USERNAME%' --email '%EMAIL%' --name '%DISPLAY_NAME%'"

echo.
pause
