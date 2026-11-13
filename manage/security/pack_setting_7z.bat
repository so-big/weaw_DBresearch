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
    color 0C
    echo ======================================================================
    echo  [ERROR] ไม่พบไฟล์ setting.txt ใน root directory
    echo ======================================================================
    echo.
    echo กดปุ่มใดๆ เพื่อกลับสู่เมนูหลัก...
    pause >nul
    exit /b 1
)

set SEVENZIP="C:\Program Files\7-Zip\7z.exe"
if not exist %SEVENZIP% (
    where 7z >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set SEVENZIP=7z
    ) else (
        color 0C
        echo ======================================================================
        echo  [ERROR] ไม่พบโปรแกรม 7-Zip ในระบบ (C:\Program Files\7-Zip\7z.exe)
        echo ======================================================================
        echo.
        echo กดปุ่มใดๆ เพื่อกลับสู่เมนูหลัก...
        pause >nul
        exit /b 1
    )
)

%SEVENZIP% a -p"nuttertools@2026-2" -mhe=on setting.7z setting.txt
set ERR=%ERRORLEVEL%

echo.
if %ERR% EQU 0 (
    echo ======================================================================
    echo  [SUCCESS] เข้ารหัสไฟล์เป็น setting.7z สำเร็จ!
    echo  - รหัสผ่านที่ใช้เข้ารหัส: nuttertools@2026-2
    echo ======================================================================
) else (
    color 0C
    echo ======================================================================
    echo  [ERROR] การเข้ารหัสล้มเหลว (Error Code: %ERR%)
    echo ======================================================================
)

echo.
echo กดปุ่มใดๆ เพื่อกลับสู่เมนูหลัก...
pause >nul
exit /b %ERR%