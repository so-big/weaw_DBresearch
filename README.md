# DBresearch - ระบบถอดข้อความเอกสารสัญญาและงานวิจัย (OCR Worker System)

> **DBresearch OCR Worker** คือระบบประมวลผลและถอดข้อความเอกสารสัญญาและโครงการวิจัยความปลอดภัยสูง ทำงานร่วมกับระบบฐานข้อมูลภายนอก (MySQL) และถอดข้อความอัตโนมัติด้วย Tesseract OCR รองรับทั้งภาษาไทยและภาษาอังกฤษ

---

## 🏛 สถาปัตยกรรมระบบ (Dedicated OCR Worker Architecture)

โปรเจกต์นี้ได้รับการจัดโครงสร้างเป็นระบบประมวลผล **OCR Worker เฉพาะทาง (Dedicated Service)** โดยเชื่อมต่อกับคิวงาน MySQL ภายนอก 100%:

```
wear_DBresearch/
├── manage.bat                  # 🚀 ศูนย์ควบคุมหลัก (Central Management Console)
├── manage/                     # 📂 รวมสคริปต์จัดการระบบ (.bat)
│   ├── prod/                   # สคริปต์ควบคุมฝั่ง Production (OCR Worker)
│   │   ├── start_ocr.bat       # เริ่มต้น OCR Worker
│   │   ├── stop_ocr.bat        # หยุด OCR Worker
│   │   ├── restart_ocr.bat     # รีสตาร์ท OCR Worker
│   │   ├── status_ocr.bat      # เช็คสถานะและดู Logs
│   │   └── test_mysql.bat      # ทดสอบเชื่อมต่อ MySQL (10.27.50.43:3307)
│   └── security/               # สคริปต์ความปลอดภัยและการเข้ารหัส
│       ├── pack_setting_7z.bat # เข้ารหัส setting.txt -> setting.7z ด้วย 7-Zip
│       └── unpack_setting_7z.bat # ถอดรหัส setting.7z -> setting.txt
├── docker-compose.yml          # 🏭 Production Compose (OCR Worker เชื่อมต่อ MySQL)
├── setting.txt                 # 🔑 ไฟล์ตั้งค่าหลัก (Single Source of Truth - Gitignored)
├── setting.txt.example         # 📄 ไฟล์เทมเพลตสำหรับผู้ใช้ใหม่
├── setting.7z                  # 🔒 ไฟล์คอนฟิกที่ถูกเข้ารหัสด้วย 7-Zip (ปลอดภัยบน Git)
├── docs/                       # 📚 เอกสารคู่มือและการออกแบบระบบ
└── src/dbresearch/             # 💻 ซอร์สโค้ด Python (OCR Engine & MySQL Worker Adapter)
```

---

## 🚀 การจัดการระบบผ่าน `manage.bat` (Central Console)

เพียงดับเบิลคลิกไฟล์ **`manage.bat`** ที่ Root โฟลเดอร์ จะพบเมนูควบคุมระบบทั้งหมด:

```text
======================================================================
            DBresearch Management Console (ระบบจัดการ OCR Worker)
======================================================================

  [OCR WORKER MANAGEMENT]
    1. Start Production OCR Worker   (เปิดเซิร์ฟเวอร์ OCR)
    2. Stop Production OCR Worker    (ปิดเซิร์ฟเวอร์ OCR)
    3. Restart Production OCR Worker (รีสตาร์ท OCR Worker)
    4. OCR Worker Status and Logs    (ตรวจเช็คสถานะและ Log ล่าสุด)
    5. Test MySQL Connection         (ทดสอบเชื่อมต่อ 10.27.50.43:3307)

  [SECURITY AND CREDENTIALS]
    6. Encrypt setting.txt to 7z     (เข้ารหัส setting.7z ด้วย 7-Zip)
    7. Decrypt setting.7z to txt     (ถอดรหัส setting.7z กลับมาใช้งาน)

    0. Exit                          (ออกจากโปรแกรม)
======================================================================
```

---

## ⚙️ การตั้งค่า `setting.txt` (Single Source of Truth)

ไฟล์ `setting.txt` รวมศูนย์การตั้งค่าทุกส่วนไว้ในไฟล์เดียว:
- บรรทัดที่ขึ้นต้นด้วย `#` หรือบรรทัดว่าง ระบบจะ**ข้ามการอ่าน**
- ปรับแต่งค่าของ MySQL Server ได้ทันที:

```ini
[mysql]
host = 10.27.50.43
port = 3307
database = weaw_dbresearch
username = weaw_ocr
password = your_password_here
ssl_ca = mysql-ca.pem
```

---

## 🤖 MySQL OCR Worker Adapter (`src/dbresearch/mysql_adapter.py`)

- **`CALL ocr_claim_job(worker_id)`:** ดึงงาน OCR จากคิว MySQL (0 แถว = ปกติเมื่อไม่มีคิวงาน)
- **`CALL ocr_heartbeat(job_id, worker_id)`:** ส่ง Heartbeat สัญญาณการประมวลผล
- **`CALL ocr_complete_job(job_id, worker_id, result_json, extracted_meta)`:** ส่งผลลัพธ์ข้อความ OCR
- **`CALL ocr_fail_job(job_id, worker_id, error_message, can_retry)`:** แจ้งข้อผิดพลาด
- บังคับใช้ TLS, UTF-8 (`utf8mb4`), UTC และตรวจเช็ค SHA-256 PDF Hash ก่อนเริ่มงาน
