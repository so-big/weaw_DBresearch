# คู่มือการใช้งาน DBresearch บนเครื่องนี้ (Docker บนไดรว์ E:\wear_DBresearch)

ระบบฐานข้อมูลและจัดเก็บเอกสารสัญญา/งานวิจัยที่มีการเข้ารหัสข้อมูล (DBresearch) ติดตั้งและตั้งค่าเรียบร้อยแล้วบนไดรว์ `E:\wear_DBresearch` โดยแยกเซิร์ฟเวอร์ OCR และเว็บ ออกจากกันตามความต้องการ

---

## 🚀 สรุปไฟล์ .bat สำหรับควบคุมระบบ

| ไฟล์ .bat | การทำงาน |
|---|---|
| **`1_START_OCR_SERVER.bat`** | **เปิดเซิร์ฟเวอร์ OCR** (Container: `dbresearch-ocr`) พร้อม Database |
| **`2_START_WEB_SERVER.bat`** | **เปิดเซิร์ฟเวอร์เว็บ** (Container: `dbresearch-web`) และเปิด Browser ไปที่ `http://localhost:8120` |
| **`START_ALL.bat`** | **เปิดทั้งหมดในคลิกเดียว** (เปิด OCR ก่อน จากนั้นเปิด Web ให้อัตโนมัติ) |
| **`STOP_OCR_SERVER.bat`** | **ปิดเฉพาะเซิร์ฟเวอร์ OCR** (ช่วยประหยัด RAM/CPU เมื่อไม่ได้อัปโหลดเอกสาร) |
| **`RESTART_OCR_SERVER.bat`** | รีสตาร์ทเซิร์ฟเวอร์ OCR |
| **`STOP_WEB_SERVER.bat`** | ปิดเฉพาะเซิร์ฟเวอร์เว็บ |
| **`RESTART_WEB_SERVER.bat`** | รีสตาร์ทเซิร์ฟเวอร์เว็บ |
| **`STOP_ALL.bat`** | ปิดการทำงานทุกบริการทั้งหมด (Web, OCR, Database) |
| **`STATUS.bat`** | ตรวจสอบสถานะการทำงานของ Containers และ Health Check |
| **`CREATE_ADMIN.bat`** | สร้างบัญชีผู้ดูแลระบบ (Admin) เพิ่มเติม |

---

## 📌 ขั้นตอนการใช้งานปกติ

1. ดับเบิ้ลคลิก **`1_START_OCR_SERVER.bat`** เพื่อเปิดเซิร์ฟเวอร์ OCR
2. ดับเบิ้ลคลิก **`2_START_WEB_SERVER.bat`** เพื่อเปิดเซิร์ฟเวอร์เว็บ (ระบบจะเช็คและแจ้งเตือนสถานะ OCR ให้ทันที)
3. ระบบจะเปิดเว็บเบราว์เซอร์ไปที่: **`http://localhost:8120`**

*(หรือหากต้องการเปิดทุกอย่างพร้อมกันในคลิกเดียว สามารถกด **`START_ALL.bat`** ได้เลย)*

---

## 🔑 ข้อมูลเข้าสู่ระบบเริ่มต้น

- **URL:** [http://localhost:8120](http://localhost:8120)
- **Username:** `admin`
- **Password:** `admin123456`
- **API Docs:** [http://localhost:8120/api/docs](http://localhost:8120/api/docs)

---

## 📁 การจัดเก็บข้อมูลบนไดรว์ E:

- **ที่ตั้งโปรเจกต์:** `E:\wear_DBresearch`
- **ไฟล์เอกสารที่เข้ารหัส (Blobs):** `E:\wear_DBresearch\data\blobs` (จัดเก็บบนไดรว์ E: ทั้งหมด)
- **กุญแจเข้ารหัส Master Key (KEK):** `E:\wear_DBresearch\secrets\kek.json` *(สำคัญมาก: ห้ามลบเด็ดขาด)*
- **การตั้งค่า Environment:** `E:\wear_DBresearch\.env`
