@echo off
@chcp 65001 >nul
title Restart Production OCR Worker
color 0B

echo ======================================================================
echo           Restarting DBresearch Production OCR Worker...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose restart ocr"

echo.
echo ======================================================================
echo  [SUCCESS] Production OCR Worker restarted.
echo ======================================================================
echo.
pause
