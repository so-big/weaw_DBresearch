# AGENTS.md — Developer & AI Agent Knowledge Base

เอกสารนี้รวบรวมกฎเหล็ก สถาปัตยกรรมระบบ ข้อกำหนดด้านความปลอดภัย และคู่มือการพัฒนาระบบ **DBresearch** สำหรับ AI Agents และทีมนักพัฒนา

---

## 1. ภาพรวมระบบ (System Overview)

- **โครงการ:** DBresearch (ระบบจัดเก็บ สืบค้น และถอดข้อความเอกสารสัญญา/งานวิจัย)
- **Frontend / API:** Svelte 5 + Vite, FastAPI (Python 3.13), Uvicorn
- **ความปลอดภัยของเอกสาร:** เข้ารหัสทุกไฟล์ด้วย Envelope Encryption (Google Tink AES-256-GCM) ผ่าน Master Key (KEK)
- **เครื่องยนต์ OCR:** Tesseract OCR รองรับภาษาไทย (`tha`) และภาษาอังกฤษ (`eng`)
- **การจัดเก็บข้อมูล:**
  - ไดเรกทอรีโปรเจกต์: `E:\wear_DBresearch`
  - ไฟล์เอกสารที่เข้ารหัส (Ciphertext blobs): `E:\wear_DBresearch\data\blobs`
  - Master Key (KEK): `E:\wear_DBresearch\secrets\kek.json` *(ห้ามลบ ห้ามแก้ ห้ามนำขึ้น Git)*

---

## 2. กฎเหล็กด้านความปลอดภัย (Security Rules — Do Not Break)

1. **ห้ามนำรหัสผ่านจริงและ Token ขึ้น Git หรือพิมพ์ลง Console Log เด็ดขาด:**
   - รหัสผ่านจริงในไฟล์ `setting.txt` ต้องไม่ถูกพิมพ์ออกมาใน log หรือตอบกลับใน chat
   - ไฟล์ `setting.txt` ต้องอยู่ใน `.gitignore` เสมอ
2. **การอัปโหลดการตั้งค่าขึ้น Git ด้วย 7-Zip:**
   - เมื่อต้องการนำไฟล์ `setting.txt` ขึ้น Git ให้ใช้ `PACK_SETTING_7Z.bat` เพื่อบีบอัดเป็น `setting.7z` ด้วยรหัสผ่าน:
     `nuttertools@2026-2` (เปิด `-mhe=on` เข้ารหัสทั้ง Header และ Data)
   - ไฟล์ `setting.7z` อนุญาตให้อยู่บน Git ได้
   - คลายไฟล์เพื่อใช้งานด้วย `UNPACK_SETTING_7Z.bat`
   - ยกเลิกการใช้งานไฟล์ `.json` สำหรับเก็บรหัสผ่านแล้ว
3. **ห้ามยุ่งกับฐานข้อมูล Production นอกเหนือจาก Stored Procedures:**
   - ห้ามสั่ง `DROP TABLE`, `CREATE TABLE` หรือแก้ไขสิทธิ์ในฐานข้อมูล Production ของหน่วยงาน
   - ฐานข้อมูลจริงมีโครงสร้างพร้อมแล้ว ให้อ้างอิงตาม `schema-reference.sql` และ `routines-reference.sql`

---

## 3. การกำหนดค่าระบบ (`setting.txt` — Single Source of Truth)

ระบบกำหนดให้ไฟล์ `setting.txt` เป็นศูนย์กลางการกำหนดค่าเพียงไฟล์เดียว:
- **กฎการอ่านไฟล์:** บรรทัดที่ขึ้นต้นด้วย `#` หรือบรรทัดว่าง ระบบจะข้ามการอ่าน (Comments)
- **โครงสร้าง:** แยกตาม Section เช่น `[web]` และ `[mysql]` รูปแบบ `key = value`
- **ค่าเริ่มต้นที่สำคัญ:**
  ```ini
  [web]
  port = 8120
  username = admin
  password = admin123456

  [mysql]
  host = 10.27.50.43
  port = 3307
  database = weaw_dbresearch
  username = weaw_ocr
  password = <real_password>
  ssl_ca = mysql-ca.pem
  ```

---

## 4. มาตรฐานของ MySQL OCR Worker Adapter (`src/dbresearch/mysql_adapter.py`)

Worker รับงาน OCR จากเซิร์ฟเวอร์ MySQL ผ่าน Stored Procedures โดยมีข้อกำหนดทางเทคนิคดังนี้:

1. **Stored Procedures:**
   - `CALL ocr_claim_job(worker_id)` — ดึงงานถัดไป (หากไม่มีงานในคิว ผลลัพธ์ 0 แถวถือเป็นสภาวะปกติ ให้รอรอบถัดไป)
   - `CALL ocr_heartbeat(job_id, worker_id)` — ส่งสัญญาณทำงานต่อเนื่องป้องกันงานหลุดคิว
   - `CALL ocr_complete_job(job_id, worker_id, result_json, extracted_meta)` — ส่งผลลัพธ์ข้อความ OCR
   - `CALL ocr_fail_job(job_id, worker_id, error_message, can_retry)` — แจ้งกรณีประมวลผลล้มเหลว
2. **มาตรฐานการเชื่อมต่อ:**
   - บังคับใช้ TLS พร้อมตรวจ CA (`mysql-ca.pem`) และตรวจ Hostname
   - บังคับใช้ Encoding `utf8mb4` และ Timezone `UTC` (`SET time_zone = '+00:00'`)
   - **ต้องปิดและเคลียร์ Result sets ทุกครั้ง:** ใช้ `while cursor.nextset(): pass` เสมอ เพื่อป้องกันปัญหา `Commands out of sync`
3. **การตรวจสอบไฟล์ (Integrity):**
   - ตรวจสอบ SHA-256 Hash ของไฟล์ PDF เทียบกับค่าในคิวงานก่อนเริ่มประมวลผล OCR เสมอ

---

## 5. การควบคุม Container บน Windows ผ่านไฟล์ `.bat`

ระบบแยก Container ระหว่าง Web Server และ OCR Server เป็นอิสระจากกัน:
- **ลำดับการเปิดใช้งาน:** หากต้องการใช้ระบบ OCR ต้องเปิด OCR Server ก่อน แล้วค่อยเปิด Web Server
  - `1_START_OCR_SERVER.bat` — เริ่มต้น PostgreSQL และ OCR Worker Container (`dbresearch-ocr`)
  - `2_START_WEB_SERVER.bat` — เริ่มต้น Web Server Container (`dbresearch-web`) และเด้งเปิดเบราว์เซอร์
  - `START_ALL.bat` — เปิดทั้งระบบตามลำดับในคลิกเดียว
  - `STOP_OCR_SERVER.bat` / `STOP_WEB_SERVER.bat` — ปิดเฉพาะส่วนเพื่อประหยัดทรัพยากร
  - `STATUS.bat` — ตรวจสอบสถานะ Containers ทั้งหมด
  - `TEST_MYSQL.bat` — รันสคริปต์ทดสอบการเชื่อมต่อไปยัง MySQL 10.27.50.43:3307

---

## 6. ข้อตกลงการพัฒนาและการ Push ขึ้น Git (Workflow Conventions)

- **นับรอบการอัปเดต:** ทำการ Commit และ Push ขึ้น GitHub ทุกๆ 3 รอบการแก้ไข หรือเมื่อผู้ใช้สั่งโดยตรง
- **การตั้งชื่อ Commit:** ใช้รูปแบบ Conventional Commits เช่น `feat: ...`, `fix: ...`, `chore: ...`
- **ไฟล์สำคัญใน Git:**
  - `setting.txt.example` (Template บน Git สำหรับผู้ใช้ใหม่)
  - `setting.7z` (ไฟล์คอนฟิกเข้ารหัสด้วยรหัสผ่าน)
