# DBresearch - ระบบจัดเก็บและสืบค้นเอกสารสัญญาและงานวิจัย (Encrypted & OCR System)

> **DBresearch** คือเว็บแอปพลิเคชันสำหรับจัดเก็บเอกสารสัญญาและโครงการวิจัยที่มีความปลอดภัยสูง พร้อมระบบเข้ารหัสข้อมูลทุกไฟล์ (Envelope Encryption ด้วย Google Tink AES-256-GCM) และระบบถอดข้อความภาษาไทย/อังกฤษอัตโนมัติด้วย Tesseract OCR เพื่อให้สามารถค้นหาเนื้อหาภายในเอกสาร PDF ได้อย่างแม่นยำ

---

## 📋 Dockerfile นี้มีไว้ทำอะไร? (Purpose of this Dockerfile)

ไฟล์ `Dockerfile` นี้ถูกออกแบบมาให้เป็น **All-in-One Container Image** ที่พร้อมใช้งานทันที:
1. **Frontend + Backend:** รวบรวมเว็บแอปพลิเคชัน (Svelte 5 + Vite) และ FastAPI Web API ในตัวเดียว
2. **OCR Engine:** ติดตั้งชุดเครื่องมือ Tesseract OCR ภาษาไทย (`tesseract-ocr-tha`) และภาษาอังกฤษ (`tesseract-ocr-eng`)
3. **Database Integration:** รองรับทั้งการต่อฐานข้อมูลภายนอก (PostgreSQL ใน Docker Compose หรือ MySQL Server ภายนอก) และการทำงานแบบ Standalone
4. **Auto Provisioning:** จัดการ Master Key (KEK), Database Migration (Alembic) และสร้าง/อัปเดตบัญชีผู้ดูแลระบบ (Admin) จากไฟล์ `setting.txt` โดยอัตโนมัติ
5. **Configurable Runtime:** สามารถปรับเปลี่ยน Port, Username และ Password ได้ง่ายดายผ่านไฟล์ `setting.txt` หรือ Environment Variables ในทุกๆ การรัน

---

## ⚙️ โครงสร้างไฟล์การตั้งค่า `setting.txt` (Configuration Structure)

ระบบใช้ไฟล์ **`setting.txt`** ที่ Root ของโปรเจกต์ในการรวมศูนย์การตั้งค่าทุกบริการ:
- **กฎการคอมเมนต์:** บรรทัดที่ขึ้นต้นด้วยเครื่องหมาย `#` หรือบรรทัดว่าง ระบบจะถือว่าเป็น Comment และ**จะไม่นำไปประมวลผล**
- **การจัดกลุ่ม:** แยกตามหมวดหมู่บริการด้วยวงเล็บก้ามปู เช่น `[web]` และ `[mysql]`
- **รูปแบบ:** กำหนดค่าแบบ `key = value` อย่างเป็นทางการ

```ini
# ======================================================================
# DBresearch Configuration File (setting.txt)
# ======================================================================
# บรรทัดที่ขึ้นต้นด้วย '#' หรือบรรทัดว่าง จะถูกข้าม (Ignored)

# ----------------------------------------------------------------------
# 1. บริการ: Web Application & API
# ----------------------------------------------------------------------
[web]
port = 8120
username = admin
password = admin123456

# ----------------------------------------------------------------------
# 2. บริการ: MySQL Database (dbroot / ฐานข้อมูลภายนอกสำหรับ OCR & ข้อมูล)
# ----------------------------------------------------------------------
[mysql]
host = 10.27.50.43
port = 3307
database = dbresearch
username = ocr_worker
password = 
ssl_ca = mysql-ca.pem
```

---

## 🔐 การจัดการรหัสผ่าน MySQL และการอัปโหลดขึ้น GitHub อย่างปลอดภัย

ตามข้อกำหนดความปลอดภัย **ห้ามนำรหัสผ่านจริงขึ้น GitHub เด็ดขาด**:
1. ไฟล์รหัสผ่าน MySQL จริงจะถูกเก็บไว้ใน `sqlpass.json` หรือ `ocr-worker-PRIVATE.json` (ซึ่งถูกใส่ไว้ใน `.gitignore` เรียบร้อยแล้ว)
2. หากต้องการนำไฟล์รหัสผ่านขึ้น GitHub ให้อัดเป็นไฟล์บีบอัด **7-Zip (`sqlpass.7z`)** พร้อมตั้งรหัสผ่าน **`nuttertools@2026-2`**:
   - **เข้ารหัสไฟล์:** ดับเบิลคลิก `PACK_SQLPASS_7Z.bat` (จะสร้าง `sqlpass.7z` ที่เข้ารหัสและนำขึ้น Git ได้อย่างปลอดภัย)
   - **ถอดรหัสไฟล์:** ดับเบิลคลิก `UNPACK_SQLPASS_7Z.bat` (จะคลายไฟล์ `sqlpass.json` ออกมาใช้งาน)

---

## 🤖 MySQL OCR Worker Adapter (การรับงานและส่งผลกับ MySQL 10.27.50.43:3307)

OCR Worker รองรับการเชื่อมต่อกับ MySQL Server ตามข้อกำหนดผ่านโมดูล `src/dbresearch/mysql_adapter.py`:

### 1. Stored Procedures ที่รองรับ
- **`CALL ocr_claim_job(worker_id)`:** ดึงงาน OCR ลำดับถัดไปจากคิว (หากไม่มีคิวงาน คืนค่า 0 แถว ถือเป็นผลปกติ)
- **`CALL ocr_heartbeat(job_id, worker_id)`:** ส่งสัญญาณ Heartbeat ขณะกำลังประมวลผลเอกสาร
- **`CALL ocr_complete_job(job_id, worker_id, result_json, extracted_meta)`:** ส่งผลลัพธ์ข้อความ OCR และ Metadata เมื่อเสร็จสิ้น
- **`CALL ocr_fail_job(job_id, worker_id, error_message, can_retry)`:** แจ้งข้อผิดพลาดพร้อมสถานะการลองใหม่ (Retry)

### 2. มาตรฐานความปลอดภัยและข้อกำหนดทางเทคนิค
- **TLS/SSL:** ตรวจสอบ CA (`mysql-ca.pem`) และตรวจสอบ Hostname อย่างเคร่งครัด
- **Encoding & Timezone:** รองรับ UTF-8 (`utf8mb4`) และเวลาสากล `UTC`
- **Result Sets:** ปิดและเคลียร์ Result sets ทุกรอบ (`cursor.nextset()`) เพื่อป้องกัน Connection lock
- **Data Integrity:** ตรวจสอบ SHA-256 Hash ของไฟล์ PDF ก่อนเริ่มประมวลผล OCR
- **Security:** ไม่พิมพ์รหัสผ่าน Token หรือข้อความในเอกสารลง Log

### 3. การทดสอบการเชื่อมต่อ MySQL
สามารถทดสอบการเชื่อมต่อได้โดยดับเบิลคลิก:
- **`TEST_MYSQL.bat`** (หรือรัน `python -m dbresearch.mysql_adapter`)

---

## 🖥 การใช้งานบน Windows ผ่านไฟล์ `.bat`

| ไฟล์ `.bat` | หน้าที่การทำงาน |
|---|---|
| **`1_START_OCR_SERVER.bat`** | **เปิดเซิร์ฟเวอร์ OCR** (Container: `dbresearch-ocr`) |
| **`2_START_WEB_SERVER.bat`** | **เปิดเว็บจริง** (Container: `dbresearch-web`) และเปิด Browser ให้อัตโนมัติ |
| **`START_ALL.bat`** | **เปิดทั้งหมดตามลำดับ** (เปิด OCR Server ก่อน แล้วค่อยเปิดเว็บจริง) |
| **`STOP_OCR_SERVER.bat`** | ปิดเฉพาะเซิร์ฟเวอร์ OCR (ช่วยประหยัด CPU/RAM) |
| **`RESTART_OCR_SERVER.bat`** | รีสตาร์ทเซิร์ฟเวอร์ OCR |
| **`STOP_WEB_SERVER.bat`** | ปิดเฉพาะเซิร์ฟเวอร์เว็บ |
| **`RESTART_WEB_SERVER.bat`** | รีสตาร์ทเซิร์ฟเวอร์เว็บ |
| **`STOP_ALL.bat`** | ปิดการทำงานของระบบทั้งหมด |
| **`STATUS.bat`** | แสดงสถานะของ Container ทุกตัว และตรวจสอบ Health Check |
| **`TEST_MYSQL.bat`** | **ทดสอบการเชื่อมต่อไปยัง MySQL Server (10.27.50.43:3307)** |
| **`PACK_SQLPASS_7Z.bat`** | **บีบอัดและเข้ารหัส `sqlpass.json` เป็น `sqlpass.7z` ด้วยรหัสผ่าน `nuttertools@2026-2`** |
| **`UNPACK_SQLPASS_7Z.bat`** | ถอดรหัส `sqlpass.7z` ออกมาเป็น `sqlpass.json` |
