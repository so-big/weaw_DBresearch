@echo off
@chcp 65001 >nul
title Unpack setting.7z to setting.txt
color 0A

echo ======================================================================
echo       ถอดรหัสไฟล์ setting.7z เป็น setting.txt ด้วย 7-Zip
echo ======================================================================
echo.

if not exist setting.7z (
    echo [ERROR] ไม่พบไฟล์ setting.7z ในโฟลเดอร์นี้
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

%SEVENZIP% x -p"nuttertools@2026-2" -y setting.7z

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo  [SUCCESS] ถอดรหัสไฟล์ setting.txt สำเร็จ พร้อมใช้งานทันที!
    echo ======================================================================
) else (
    echo.
    echo [ERROR] การถอดรหัสล้มเหลว กรุณาตรวจสอบรหัสผ่าน
)

echo.
pause
