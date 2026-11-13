# ======================================================================
# DBresearch OCR Worker - Management Console (PowerShell Engine)
# รองรับภาษาไทย 100% บนทุกเวอร์ชันของ Windows โดยใช้ UTF-8 DirectWrite
# ======================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "DBresearch OCR Management Console"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Show-Header {
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "            DBresearch Management Console (ระบบจัดการ OCR Worker)" -ForegroundColor Cyan
    Write-Host "======================================================================" -ForegroundColor Cyan
}

function Show-Menu {
    Clear-Host
    Show-Header
    Write-Host ""
    Write-Host "  [OCR WORKER MANAGEMENT - ควบคุมระบบถอดข้อความ]" -ForegroundColor Yellow
    Write-Host "    1. Start Production OCR Worker   (เปิดเซิร์ฟเวอร์ OCR)" -ForegroundColor White
    Write-Host "    2. Stop Production OCR Worker    (ปิดเซิร์ฟเวอร์ OCR)" -ForegroundColor White
    Write-Host "    3. Restart Production OCR Worker (รีสตาร์ท OCR Worker)" -ForegroundColor White
    Write-Host "    4. OCR Worker Status and Logs    (ตรวจเช็คสถานะและดู Log ล่าสุด)" -ForegroundColor White
    Write-Host "    5. Test MySQL Connection         (ทดสอบเชื่อมต่อ 10.27.50.43:3307)" -ForegroundColor White
    Write-Host ""
    Write-Host "  [SECURITY AND CREDENTIALS - ความปลอดภัยและรหัสผ่าน]" -ForegroundColor Yellow
    Write-Host "    6. Encrypt setting.txt to 7z     (เข้ารหัส setting.7z ด้วย 7-Zip)" -ForegroundColor White
    Write-Host "    7. Decrypt setting.7z to txt     (ถอดรหัส setting.7z กลับมาใช้งาน)" -ForegroundColor White
    Write-Host ""
    Write-Host "    0. Exit                          (ออกจากโปรแกรม)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Cyan
}

function Action-Start {
    Write-Host "`nกำลังเริ่มต้นเปิดเซิร์ฟเวอร์ OCR Worker..." -ForegroundColor Cyan
    wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose up -d ocr"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[สำเร็จ] OCR Worker เริ่มทำงานในตู้คอนเทนเนอร์เรียบร้อยแล้ว!" -ForegroundColor Green
        Write-Host "  - คอนเทนเนอร์: dbresearch-ocr" -ForegroundColor Green
        Write-Host "  - คิวงานหลัก:  MySQL (10.27.50.43:3307)" -ForegroundColor Green
    } else {
        Write-Host "`n[ผิดพลาด] ไม่สามารถเริ่มทำงานได้ (Error Code: $LASTEXITCODE)" -ForegroundColor Red
        Write-Host "  - กรุณาตรวจสอบว่า Docker Desktop กำลังเปิดใช้งานอยู่หรือไม่" -ForegroundColor Red
    }
}

function Action-Stop {
    Write-Host "`nกำลังหยุดการทำงานของ OCR Worker..." -ForegroundColor Yellow
    wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose stop ocr"
    Write-Host "`n[สำเร็จ] หยุดการทำงานของ OCR Worker เรียบร้อยแล้ว" -ForegroundColor Green
}

function Action-Restart {
    Write-Host "`nกำลังรีสตาร์ท OCR Worker..." -ForegroundColor Cyan
    wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose restart ocr"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[สำเร็จ] OCR Worker รีสตาร์ทเรียบร้อยแล้ว" -ForegroundColor Green
    } else {
        Write-Host "`n[ผิดพลาด] ไม่สามารถรีสตาร์ทได้ (Error Code: $LASTEXITCODE)" -ForegroundColor Red
    }
}

function Action-Status {
    Write-Host "`n--- 1. สถานะตู้คอนเทนเนอร์ (Container Status) ---" -ForegroundColor Cyan
    wsl bash -c "docker ps --filter name=dbresearch-ocr --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
    Write-Host "`n--- 2. บันทึกการทำงานล่าสุด (Recent Logs - 25 บรรทัด) ---" -ForegroundColor Cyan
    wsl bash -c "docker logs dbresearch-ocr --tail 25"
    Write-Host "----------------------------------------------------------------------" -ForegroundColor Cyan
}

function Action-TestMySQL {
    Write-Host "`nกำลังทดสอบเชื่อมต่อไปยังฐานข้อมูล MySQL (10.27.50.43:3307)..." -ForegroundColor Cyan
    wsl bash -c "cd /mnt/e/wear_DBresearch && docker compose run --rm --no-deps ocr python -m dbresearch.mysql_adapter"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[สำเร็จ] ทดสอบเชื่อมต่อ MySQL และ Stored Procedures ผ่านเรียบร้อย!" -ForegroundColor Green
    } else {
        Write-Host "`n[หมายเหตุ] ไม่สามารถติดต่อ MySQL ได้ในขณะนี้" -ForegroundColor Yellow
        Write-Host "  - หากเครื่องนี้อยู่นอกเครือข่าย กรุณาเปิด VPN ของหน่วยงานก่อน" -ForegroundColor Yellow
        Write-Host "  - ตรวจสอบความถูกต้องของ host, port, username, password ใน setting.txt" -ForegroundColor Yellow
    }
}

function Action-Pack7z {
    Write-Host "`nกำลังนำไฟล์ setting.txt ไปบีบอัดและใส่รหัสผ่านด้วย 7-Zip..." -ForegroundColor Cyan
    if (-not (Test-Path "setting.txt")) {
        Write-Host "`n[ผิดพลาด] ไม่พบไฟล์ setting.txt ใน root directory" -ForegroundColor Red
        return
    }
    $7z = "C:\Program Files\7-Zip\7z.exe"
    if (-not (Test-Path $7z)) {
        where.exe 7z 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $7z = "7z" } else {
            Write-Host "`n[ผิดพลาด] ไม่พบโปรแกรม 7-Zip ในเครื่อง (C:\Program Files\7-Zip\7z.exe)" -ForegroundColor Red
            return
        }
    }
    & $7z a -p"nuttertools@2026-2" -mhe=on setting.7z setting.txt
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[สำเร็จ] เข้ารหัสไฟล์ setting.7z เรียบร้อยแล้ว!" -ForegroundColor Green
        Write-Host "  - รหัสผ่าน: nuttertools@2026-2" -ForegroundColor Green
        Write-Host "  - พร้อมสำหรับการ Commit และ Push ขึ้น GitHub อย่างปลอดภัย" -ForegroundColor Green
    } else {
        Write-Host "`n[ผิดพลาด] การเข้ารหัสล้มเหลว (Error Code: $LASTEXITCODE)" -ForegroundColor Red
    }
}

function Action-Unpack7z {
    Write-Host "`nกำลังถอดรหัส setting.7z เป็น setting.txt..." -ForegroundColor Cyan
    if (-not (Test-Path "setting.7z")) {
        Write-Host "`n[ผิดพลาด] ไม่พบไฟล์ setting.7z ใน root directory" -ForegroundColor Red
        return
    }
    $7z = "C:\Program Files\7-Zip\7z.exe"
    if (-not (Test-Path $7z)) {
        where.exe 7z 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $7z = "7z" } else {
            Write-Host "`n[ผิดพลาด] ไม่พบโปรแกรม 7-Zip ในเครื่อง (C:\Program Files\7-Zip\7z.exe)" -ForegroundColor Red
            return
        }
    }
    & $7z x -y -p"nuttertools@2026-2" setting.7z
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[สำเร็จ] ถอดรหัสไฟล์ setting.txt เรียบร้อยแล้ว พร้อมใช้งานทันที!" -ForegroundColor Green
    } else {
        Write-Host "`n[ผิดพลาด] การถอดรหัสล้มเหลว รหัสผ่านอาจไม่ถูกต้อง" -ForegroundColor Red
    }
}

# ประมวลผลกรณีส่ง Arguments ผ่าน CLI
$arg = if ($args.Count -gt 0) { $args[0].ToLower() } else { "" }

switch ($arg) {
    "start"   { Action-Start; Write-Host "`nกดปุ่ม Enter เพื่อออก..."; try { try { Read-Host | Out-Null } catch {} } catch {}; exit 0 }
    "stop"    { Action-Stop; Write-Host "`nกดปุ่ม Enter เพื่อออก..."; try { try { Read-Host | Out-Null } catch {} } catch {}; exit 0 }
    "restart" { Action-Restart; Write-Host "`nกดปุ่ม Enter เพื่อออก..."; try { try { Read-Host | Out-Null } catch {} } catch {}; exit 0 }
    "status"  { Action-Status; Write-Host "`nกดปุ่ม Enter เพื่อออก..."; try { try { Read-Host | Out-Null } catch {} } catch {}; exit 0 }
    "test"    { Action-TestMySQL; Write-Host "`nกดปุ่ม Enter เพื่อออก..."; try { try { Read-Host | Out-Null } catch {} } catch {}; exit 0 }
    "pack"    { Action-Pack7z; Write-Host "`nกดปุ่ม Enter เพื่อออก..."; try { try { Read-Host | Out-Null } catch {} } catch {}; exit 0 }
    "unpack"  { Action-Unpack7z; Write-Host "`nกดปุ่ม Enter เพื่อออก..."; try { try { Read-Host | Out-Null } catch {} } catch {}; exit 0 }
}

# เมนู Interactive แบบวนซ้ำ ไม่ปิดตัวเอง
while ($true) {
    Show-Menu
    $choice = Read-Host "เลือกเมนูการทำงาน [0-7]"
    switch ($choice) {
        "1" { Action-Start; Write-Host "`nกดปุ่ม Enter เพื่อกลับสู่เมนูหลัก..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "2" { Action-Stop; Write-Host "`nกดปุ่ม Enter เพื่อกลับสู่เมนูหลัก..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "3" { Action-Restart; Write-Host "`nกดปุ่ม Enter เพื่อกลับสู่เมนูหลัก..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "4" { Action-Status; Write-Host "`nกดปุ่ม Enter เพื่อกลับสู่เมนูหลัก..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "5" { Action-TestMySQL; Write-Host "`nกดปุ่ม Enter เพื่อกลับสู่เมนูหลัก..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "6" { Action-Pack7z; Write-Host "`nกดปุ่ม Enter เพื่อกลับสู่เมนูหลัก..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "7" { Action-Unpack7z; Write-Host "`nกดปุ่ม Enter เพื่อกลับสู่เมนูหลัก..." -ForegroundColor Gray; try { Read-Host | Out-Null } catch {} }
        "0" {
            Write-Host "`nขอบคุณที่ใช้งาน DBresearch Management Console" -ForegroundColor Cyan
            Start-Sleep -Milliseconds 600
            exit
        }
        default {
            Write-Host "`n[ข้อผิดพลาด] ตัวเลือกไม่ถูกต้อง กรุณาพิมพ์ตัวเลข 0 ถึง 7 เท่านั้น" -ForegroundColor Red
            Start-Sleep -Seconds 2
        }
    }
}
