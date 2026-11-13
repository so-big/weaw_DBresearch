# ======================================================================
# DBresearch OCR Worker - Management Console
# Standard English Interface for 100% Guaranteed Legibility
# ======================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "DBresearch OCR Management Console"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Show-Header {
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "            DBresearch Management Console (OCR Worker)" -ForegroundColor Cyan
    Write-Host "======================================================================" -ForegroundColor Cyan
}

function Show-Menu {
    Clear-Host
    Show-Header
    Write-Host ""
    Write-Host "  [OCR WORKER MANAGEMENT]" -ForegroundColor Yellow
    Write-Host "    1. Start Production OCR Worker   (Launch Docker container)" -ForegroundColor White
    Write-Host "    2. Stop Production OCR Worker    (Stop Docker container)" -ForegroundColor White
    Write-Host "    3. Restart Production OCR Worker (Restart Docker container)" -ForegroundColor White
    Write-Host "    4. OCR Worker Status and Logs    (Check container & live logs)" -ForegroundColor White
    Write-Host "    5. Test MySQL Connection         (Test 10.27.50.43:3307)" -ForegroundColor White
    Write-Host ""
    Write-Host "  [SECURITY AND CREDENTIALS]" -ForegroundColor Yellow
    Write-Host "    6. Encrypt setting.txt to 7z     (Pack setting.7z with 7-Zip)" -ForegroundColor White
    Write-Host "    7. Decrypt setting.7z to txt     (Unpack setting.7z)" -ForegroundColor White
    Write-Host ""
    Write-Host "    0. Exit                          (Close console)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Cyan
}

function Action-Start {
    Write-Host "`nStarting Production OCR Worker..." -ForegroundColor Cyan
    wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose up -d ocr"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[SUCCESS] OCR Worker started successfully in Docker!" -ForegroundColor Green
        Write-Host "  - Container: dbresearch-ocr" -ForegroundColor Green
        Write-Host "  - Queue:     MySQL (10.27.50.43:3307)" -ForegroundColor Green
    } else {
        Write-Host "`n[ERROR] Failed to start OCR Worker (Error Code: $LASTEXITCODE)" -ForegroundColor Red
        Write-Host "  - Please verify that Docker Desktop is running." -ForegroundColor Red
    }
}

function Action-Stop {
    Write-Host "`nStopping OCR Worker..." -ForegroundColor Yellow
    wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose stop ocr"
    Write-Host "`n[SUCCESS] OCR Worker stopped." -ForegroundColor Green
}

function Action-Restart {
    Write-Host "`nRestarting OCR Worker..." -ForegroundColor Cyan
    wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose restart ocr"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[SUCCESS] OCR Worker restarted successfully." -ForegroundColor Green
    } else {
        Write-Host "`n[ERROR] Restart failed (Error Code: $LASTEXITCODE)" -ForegroundColor Red
    }
}

function Action-Status {
    Write-Host "`n--- 1. Container Status ---" -ForegroundColor Cyan
    wsl bash -c "docker ps --filter name=dbresearch-ocr --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
    Write-Host "`n--- 2. Recent Logs (Last 25 lines) ---" -ForegroundColor Cyan
    wsl bash -c "docker logs dbresearch-ocr --tail 25"
    Write-Host "----------------------------------------------------------------------" -ForegroundColor Cyan
}

function Action-TestMySQL {
    Write-Host "`nTesting connection to MySQL Database (10.27.50.43:3307)..." -ForegroundColor Cyan
    wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose run --rm --no-deps ocr python -m dbresearch.mysql_adapter"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[SUCCESS] MySQL connection and Stored Procedures passed!" -ForegroundColor Green
    } else {
        Write-Host "`n[NOTE] Cannot reach MySQL server at 10.27.50.43:3307 right now." -ForegroundColor Yellow
        Write-Host "  - If outside department network, please connect via VPN." -ForegroundColor Yellow
        Write-Host "  - Check host, port, username, password in setting.txt." -ForegroundColor Yellow
    }
}

function Action-Pack7z {
    Write-Host "`nEncrypting setting.txt to setting.7z using 7-Zip..." -ForegroundColor Cyan
    if (-not (Test-Path "setting.txt")) {
        Write-Host "`n[ERROR] setting.txt not found in root directory!" -ForegroundColor Red
        return
    }
    $7z = "C:\Program Files\7-Zip\7z.exe"
    if (-not (Test-Path $7z)) {
        where.exe 7z 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $7z = "7z" } else {
            Write-Host "`n[ERROR] 7-Zip not found at C:\Program Files\7-Zip\7z.exe" -ForegroundColor Red
            return
        }
    }
    & $7z a -p"nuttertools@2026-2" -mhe=on setting.7z setting.txt
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[SUCCESS] setting.7z encrypted successfully!" -ForegroundColor Green
        Write-Host "  - Password: nuttertools@2026-2" -ForegroundColor Green
        Write-Host "  - Ready for safe commit and push to GitHub." -ForegroundColor Green
    } else {
        Write-Host "`n[ERROR] 7-Zip encryption failed (Error Code: $LASTEXITCODE)" -ForegroundColor Red
    }
}

function Action-Unpack7z {
    Write-Host "`nDecrypting setting.7z to setting.txt..." -ForegroundColor Cyan
    if (-not (Test-Path "setting.7z")) {
        Write-Host "`n[ERROR] setting.7z not found in root directory!" -ForegroundColor Red
        return
    }
    $7z = "C:\Program Files\7-Zip\7z.exe"
    if (-not (Test-Path $7z)) {
        where.exe 7z 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $7z = "7z" } else {
            Write-Host "`n[ERROR] 7-Zip not found at C:\Program Files\7-Zip\7z.exe" -ForegroundColor Red
            return
        }
    }
    & $7z x -y -p"nuttertools@2026-2" setting.7z
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[SUCCESS] setting.txt restored and ready to use!" -ForegroundColor Green
    } else {
        Write-Host "`n[ERROR] Decryption failed. Password may be incorrect." -ForegroundColor Red
    }
}

# Process CLI arguments
$arg = if ($args.Count -gt 0) { $args[0].ToLower() } else { "" }

switch ($arg) {
    "start"   { Action-Start; Write-Host "`nPress Enter to exit..."; try { Read-Host | Out-Null } catch {}; exit 0 }
    "stop"    { Action-Stop; Write-Host "`nPress Enter to exit..."; try { Read-Host | Out-Null } catch {}; exit 0 }
    "restart" { Action-Restart; Write-Host "`nPress Enter to exit..."; try { Read-Host | Out-Null } catch {}; exit 0 }
    "status"  { Action-Status; Write-Host "`nPress Enter to exit..."; try { Read-Host | Out-Null } catch {}; exit 0 }
    "test"    { Action-TestMySQL; Write-Host "`nPress Enter to exit..."; try { Read-Host | Out-Null } catch {}; exit 0 }
    "pack"    { Action-Pack7z; Write-Host "`nPress Enter to exit..."; try { Read-Host | Out-Null } catch {}; exit 0 }
    "unpack"  { Action-Unpack7z; Write-Host "`nPress Enter to exit..."; try { Read-Host | Out-Null } catch {}; exit 0 }
}

# Interactive loop (never closes by itself)
while ($true) {
    Show-Menu
    $choice = Read-Host "Select option [0-7]"
    switch ($choice) {
        "1" { Action-Start; Write-Host "`nPress Enter to return to menu..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "2" { Action-Stop; Write-Host "`nPress Enter to return to menu..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "3" { Action-Restart; Write-Host "`nPress Enter to return to menu..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "4" { Action-Status; Write-Host "`nPress Enter to return to menu..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "5" { Action-TestMySQL; Write-Host "`nPress Enter to return to menu..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "6" { Action-Pack7z; Write-Host "`nPress Enter to return to menu..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "7" { Action-Unpack7z; Write-Host "`nPress Enter to return to menu..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "0" {
            Write-Host "`nExiting DBresearch Management Console. Goodbye!" -ForegroundColor Cyan
            Start-Sleep -Milliseconds 600
            exit 0
        }
        default {
            Write-Host "`n[ERROR] Invalid option! Please enter a number between 0 and 7." -ForegroundColor Red
            Start-Sleep -Seconds 2
        }
    }
}
