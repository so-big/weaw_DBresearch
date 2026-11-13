@echo off
@chcp 65001 >nul
title DBresearch - Create Admin User
color 0B

echo ======================================================================
echo                  Create Admin User
echo ======================================================================
echo.

set /p USERNAME="Enter Username: "
set /p DISPLAY_NAME="Enter Display Name: "
set /p EMAIL="Enter Email: "
set /p PASSWORD="Enter Password (at least 10 characters): "

echo.
echo Creating user...
wsl bash -c "cd /mnt/e/wear_DBresearch && DBR_PASSWORD='%PASSWORD%' docker compose exec -e DBR_PASSWORD api python -m dbresearch.cli create-admin --username '%USERNAME%' --email '%EMAIL%' --name '%DISPLAY_NAME%'"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Admin user created successfully!
) else (
    echo.
    echo [ERROR] Failed to create user. Make sure Web Server is running.
)

echo.
pause
