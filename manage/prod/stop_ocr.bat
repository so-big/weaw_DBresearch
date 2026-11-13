@echo off
@chcp 65001 >nul
title Stop Production OCR Worker
color 0C

echo ======================================================================
echo           Stopping DBresearch Production OCR Worker...
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose stop ocr"

echo.
echo ======================================================================
echo  [SUCCESS] Production OCR Worker stopped.
echo ======================================================================
echo.
pause
