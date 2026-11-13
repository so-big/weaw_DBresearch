@echo off
@chcp 65001 >nul
title Pack sqlpass.json to 7z
color 0B

echo ======================================================================
echo       เข้ารหัสไฟล์รหัสผ่าน sqlpass.json เป็น sqlpass.7z ด้วย 7-Zip
echo ======================================================================
echo.

if not exist sqlpass.json (
    echo [ERROR] ไม่พบไฟล์ sqlpass.json ในโฟลเดอร์นี้
    echo กรุณาสร้าง sqlpass.json (ดูตัวอย่างจาก sqlpass.json.example)
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

%SEVENZIP% a -p"nuttertools@2026-2" -mhe=on sqlpass.7z sqlpass.json

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo  [SUCCESS] เข้ารหัสไฟล์เป็น sqlpass.7z สำเร็จ!
    echo  - สามารถนำไฟล์ sqlpass.7z ขึ้น Git ได้อย่างปลอดภัย
    echo  - รหัสผ่านที่ใช้เข้ารหัส: nuttertools@2026-2
    echo ======================================================================
) else (
    echo.
    echo [ERROR] การเข้ารหัสล้มเหลว
)

echo.
pause
