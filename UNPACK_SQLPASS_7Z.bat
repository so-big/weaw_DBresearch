@echo off
@chcp 65001 >nul
title Unpack sqlpass.7z
color 0A

echo ======================================================================
echo       ถอดรหัสไฟล์ sqlpass.7z เป็น sqlpass.json ด้วย 7-Zip
echo ======================================================================
echo.

if not exist sqlpass.7z (
    echo [ERROR] ไม่พบไฟล์ sqlpass.7z ในโฟลเดอร์นี้
    pause
    exit /b 1
)

set SEVENZIP="C:\Program Files\7-Zip\7z.exe"
if not exist %SEVENZIP% (
    where 7z >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set SEVENZIP=7z
    ) else (
        echo [ERROR] ไม่พบโปรแกรม 7-Zip ในระบบ (C:\Program Files\7-Zip\7z.exe)
        pause
        exit /b 1
    )
)

%SEVENZIP% x -p"nuttertools@2026-2" -y sqlpass.7z

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo  [SUCCESS] ถอดรหัสไฟล์ sqlpass.json สำเร็จ!
    echo ======================================================================
) else (
    echo.
    echo [ERROR] การถอดรหัสล้มเหลว กรุณาตรวจสอบรหัสผ่าน
)

echo.
pause
