@echo off
@chcp 65001 >nul
title Pack setting.txt to setting.7z
color 0B

echo ======================================================================
echo       เข้ารหัสไฟล์การตั้งค่า setting.txt เป็น setting.7z ด้วย 7-Zip
echo ======================================================================
echo.

cd /d "%~dp0\..\.."

if not exist setting.txt (
    echo [ERROR] ไม่พบไฟล์ setting.txt ใน root directory
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

%SEVENZIP% a -p"nuttertools@2026-2" -mhe=on setting.7z setting.txt

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo  [SUCCESS] เข้ารหัสไฟล์เป็น setting.7z สำเร็จ!
    echo  - รหัสผ่านที่ใช้เข้ารหัส: nuttertools@2026-2
    echo ======================================================================
) else (
    echo.
    echo [ERROR] การเข้ารหัสล้มเหลว
)

echo.
pause
