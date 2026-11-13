@chcp 65001 >nul
@echo off
title Test MySQL Connection (10.27.50.43:3307)
color 0B

echo ======================================================================
echo        ทดสอบการเชื่อมต่อไปยัง MySQL Server (10.27.50.43:3307)
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose run --rm --no-deps ocr python -m dbresearch.mysql_adapter"
set ERR=%ERRORLEVEL%

echo.
if %ERR% EQU 0 (
    echo ======================================================================
    echo  [SUCCESS] ทดสอบการเชื่อมต่อ MySQL สำเร็จ!
    echo ======================================================================
) else (
    color 0C
    echo ======================================================================
    echo  [ERROR] ไม่สามารถเชื่อมต่อ MySQL ได้ (Error Code: %ERR%)
    echo  - กรุณาตรวจสอบ Network/VPN หรือค่าการเชื่อมต่อใน setting.txt
    echo ======================================================================
)

echo.
echo กดปุ่มใดๆ เพื่อกลับสู่เมนูหลัก...
pause >nul
exit /b %ERR%