@echo off
@chcp 65001 >nul
title DBresearch Management Console

:: Check CLI arguments
if "%1"=="start" (
    call "%~dp0manage\prod\start_ocr.bat"
    exit /b %ERRORLEVEL%
)
if "%1"=="stop" (
    call "%~dp0manage\prod\stop_ocr.bat"
    exit /b %ERRORLEVEL%
)
if "%1"=="restart" (
    call "%~dp0manage\prod\restart_ocr.bat"
    exit /b %ERRORLEVEL%
)
if "%1"=="status" (
    call "%~dp0manage\prod\status_ocr.bat"
    exit /b %ERRORLEVEL%
)
if "%1"=="test" (
    call "%~dp0manage\prod\test_mysql.bat"
    exit /b %ERRORLEVEL%
)
if "%1"=="dev" (
    call "%~dp0manage\dev\start_dev.bat"
    exit /b %ERRORLEVEL%
)
if "%1"=="dev-stop" (
    call "%~dp0manage\dev\stop_dev.bat"
    exit /b %ERRORLEVEL%
)

:menu
cls
color 0B
echo ======================================================================
echo             DBresearch Management Console (ระบบจัดการโครงการ)
echo ======================================================================
echo.
echo   [PRODUCTION - OCR WORKER]
echo     1. Start Production OCR Worker   (เปิดเซิร์ฟเวอร์ OCR)
echo     2. Stop Production OCR Worker    (ปิดเซิร์ฟเวอร์ OCR)
echo     3. Restart Production OCR Worker (รีสตาร์ท OCR Worker)
echo     4. OCR Worker Status and Logs    (ตรวจเช็คสถานะและ Log ล่าสุด)
echo     5. Test MySQL Connection         (ทดสอบเชื่อมต่อ 10.27.50.43:3307)
echo.
echo   [SECURITY AND CREDENTIALS]
echo     6. Encrypt setting.txt to 7z     (เข้ารหัส setting.7z ด้วย 7-Zip)
echo     7. Decrypt setting.7z to txt     (ถอดรหัส setting.7z กลับมาใช้งาน)
echo.
echo   [DEVELOPMENT - LOCAL SANDBOX]
echo     8. Start Dev Stack (Web + DB)    (เปิดสภาพแวดล้อมทดสอบในเครื่อง)
echo     9. Stop Dev Stack                (ปิดสภาพแวดล้อมทดสอบ)
echo.
echo     0. Exit                          (ออกจากโปรแกรม)
echo.
echo ======================================================================
set choice=
set /p choice="เลือกเมนูการทำงาน [0-9]: "

if "%choice%"=="1" (
    call "%~dp0manage\prod\start_ocr.bat"
    goto menu
)
if "%choice%"=="2" (
    call "%~dp0manage\prod\stop_ocr.bat"
    goto menu
)
if "%choice%"=="3" (
    call "%~dp0manage\prod\restart_ocr.bat"
    goto menu
)
if "%choice%"=="4" (
    call "%~dp0manage\prod\status_ocr.bat"
    goto menu
)
if "%choice%"=="5" (
    call "%~dp0manage\prod\test_mysql.bat"
    goto menu
)
if "%choice%"=="6" (
    call "%~dp0manage\security\pack_setting_7z.bat"
    goto menu
)
if "%choice%"=="7" (
    call "%~dp0manage\security\unpack_setting_7z.bat"
    goto menu
)
if "%choice%"=="8" (
    call "%~dp0manage\dev\start_dev.bat"
    goto menu
)
if "%choice%"=="9" (
    call "%~dp0manage\dev\stop_dev.bat"
    goto menu
)
if "%choice%"=="0" (
    exit /b 0
)

echo [!] กรุณาเลือกตัวเลขที่ถูกต้อง
goto menu
