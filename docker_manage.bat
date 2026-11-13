@chcp 65001 >nul
@echo off
title DBresearch Management Console
call "%~dp0manage.bat" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ======================================================================
    echo  [ERROR] มีข้อผิดพลาดเกิดขึ้นในการทำงาน (Error Code: %ERRORLEVEL%)
    echo ======================================================================
    echo กดปุ่มใดๆ เพื่อออก...
    pause >nul
)