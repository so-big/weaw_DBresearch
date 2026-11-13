@chcp 65001 >nul
@echo off
title Unpack setting.7z to setting.txt
color 0B

echo ======================================================================
echo       ถอดรหัสไฟล์คอนฟิก setting.7z เป็น setting.txt ด้วย 7-Zip
echo ======================================================================
echo.

cd /d "%~dp0\..\.."

if not exist setting.7z (
    color 0C
    echo ======================================================================
    echo  [ERROR] ไม่พบไฟล์ setting.7z ใน root directory
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

%SEVENZIP% x -y -p"nuttertools@2026-2" setting.7z
set ERR=%ERRORLEVEL%

echo.
if %ERR% EQU 0 (
    echo ======================================================================
    echo  [SUCCESS] ถอดรหัสไฟล์ setting.txt สำเร็จ พร้อมใช้งาน!
    echo ======================================================================
) else (
    color 0C
    echo ======================================================================
    echo  [ERROR] การถอดรหัสล้มเหลว รหัสผ่านอาจไม่ถูกต้อง (Error Code: %ERR%)
    echo ======================================================================
)

echo.
echo กดปุ่มใดๆ เพื่อกลับสู่เมนูหลัก...
pause >nul
exit /b %ERR%