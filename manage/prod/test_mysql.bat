@echo off
@chcp 65001 >nul
title Test MySQL Connection (10.27.50.43:3307)
color 0B

echo ======================================================================
echo        ทดสอบการเชื่อมต่อไปยัง MySQL Server (10.27.50.43:3307)
echo ======================================================================
echo.

wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose run --rm --no-deps ocr python -m dbresearch.mysql_adapter"

echo.
pause
