# AGENTS.md — Developer & AI Agent Knowledge Base

เอกสารนี้รวบรวมกฎเหล็ก สถาปัตยกรรมระบบ ข้อกำหนดด้านความปลอดภัย และคู่มือการพัฒนาระบบสำหรับ AI Agents และทีมนักพัฒนา

---

## ⚠️ กฎสำคัญที่สุด: ขอบเขตการทำงาน (Scope of Responsibility)

> **"ไม่ต้องทำฝั่ง Web Server อีกต่อไปแล้ว — ให้ทำเฉพาะฝั่ง OCR เท่านั้น เนื่องจาก Web Server ย้ายไปอยู่ที่อื่นแล้ว"**

- **ขอบเขตที่ยกเลิก:** ไม่ต้องพัฒนา ปรับแต่ง หรือดูแลฝั่ง Web Server (Svelte UI / FastAPI Web Application) ในโปรเจกต์นี้อีกต่อไป
- **ขอบเขตที่รับผิดชอบเต็มตัว (OCR Worker Only):**
  1. พัฒนาและดูแล **OCR Engine & OCR Worker Adapter** (`src/dbresearch/mysql_adapter.py` และ `worker`)
  2. รับงานจากคิวฐานข้อมูล MySQL ผ่าน Stored Procedure `CALL ocr_claim_job(...)`
  3. ส่งสัญญาณ Heartbeat ระหว่างประมวลผลผ่าน `CALL ocr_heartbeat(...)`
  4. ทำการถอดข้อความภาษาไทยและอังกฤษจากไฟล์ PDF (Tesseract OCR) พร้อมสกัด Metadata
  5. ส่งผลลัพธ์กลับไปยัง MySQL ผ่าน `CALL ocr_complete_job(...)` หรือแจ้งข้อผิดพลาดผ่าน `CALL ocr_fail_job(...)`
  6. ตรวจสอบความถูกต้องของไฟล์ PDF ด้วย SHA-256 Hash ก่อนเริ่มทำ OCR

---

## 🏛 โครงสร้างสถาปัตยกรรมระบบ (OCR Worker Dedicated Stack)

โปรเจกต์นี้ได้รับการปรับแต่งเพื่อทำหน้าที่เป็น **Dedicated OCR Worker Service** เพียงอย่างเดียว:
- **ฐานข้อมูลที่ใช้:** MySQL (`10.27.50.43:3307`) เพียงตัวเดียว โดยสื่อสารผ่าน Stored Procedures ของคิวงาน
- **ตัดส่วนที่ไม่ใช้ออก 100%:** ไม่มี PostgreSQL, ไม่มี Alembic migrations, ไม่มี Local Web Server
- **Production Stack (`docker-compose.yml`):**
   - รันเฉพาะ **`dbresearch-ocr`** (Worker Container)
   - เชื่อมต่อตรงกับ MySQL ผ่านค่าใน `setting.txt`
- **ศูนย์ควบคุมสคริปต์ (`manage/` และ `manage.bat`):**
   - `manage.bat` — ศูนย์ควบคุมหลัก (Central Interactive Console)
   - `manage/prod/` — สคริปต์ควบคุม Worker (`start_ocr.bat`, `stop_ocr.bat`, `restart_ocr.bat`, `status_ocr.bat`, `test_mysql.bat`)
   - `manage/security/` — สคริปต์เข้ารหัส 7-Zip (`pack_setting_7z.bat`, `unpack_setting_7z.bat`)

---

## 1. กฎเหล็กด้านความปลอดภัย (Security Rules — Do Not Break)

1. **ห้ามนำรหัสผ่านจริงและ Token ขึ้น Git หรือพิมพ์ลง Console Log เด็ดขาด:**
   - รหัสผ่านจริงในไฟล์ `setting.txt` ต้องไม่ถูกพิมพ์ออกมาใน log หรือตอบกลับใน chat
   - ไฟล์ `setting.txt` ต้องอยู่ใน `.gitignore` เสมอ
2. **การอัปโหลดการตั้งค่าขึ้น Git ด้วย 7-Zip:**
   - เมื่อต้องการนำไฟล์ `setting.txt` ขึ้น Git ให้ใช้ `manage/security/pack_setting_7z.bat` เพื่อบีบอัดเป็น `setting.7z` ด้วยรหัสผ่าน:
     `nuttertools@2026-2` (เปิด `-mhe=on` เข้ารหัสทั้ง Header และ Data)
   - ไฟล์ `setting.7z` อนุญาตให้อยู่บน Git ได้
   - คลายไฟล์เพื่อใช้งานด้วย `manage/security/unpack_setting_7z.bat`
3. **ห้ามยุ่งกับฐานข้อมูล Production นอกเหนือจาก Stored Procedures:**
   - ห้ามสั่ง `DROP TABLE`, `CREATE TABLE` หรือแก้ไขสิทธิ์ในฐานข้อมูล Production ของหน่วยงาน
   - ฐานข้อมูลจริงมีโครงสร้างพร้อมแล้ว

---

## 2. การกำหนดค่าระบบ (`setting.txt` — Single Source of Truth)

- **กฎการอ่านไฟล์:** บรรทัดที่ขึ้นต้นด้วย `#` หรือบรรทัดว่าง ระบบจะข้ามการอ่าน (Comments)
- **โครงสร้าง:** แยกตาม Section โดยเฉพาะหมวดหมู่ `[mysql]` รูปแบบ `key = value`
- **ค่ากำหนดการเชื่อมต่อ MySQL:**
  ```ini
  [mysql]
  host = 10.27.50.43
  port = 3307
  database = weaw_dbresearch
  username = weaw_ocr
  password = <real_password>
  ssl_ca = mysql-ca.pem
  ```

---

## 3. มาตรฐานของ MySQL OCR Worker Adapter (`src/dbresearch/mysql_adapter.py`)

1. **Stored Procedures:**
   - `CALL ocr_claim_job(worker_id)` — ดึงงานถัดไป (0 แถว = สภาวะปกติเมื่อไม่มีคิวงาน)
   - `CALL ocr_heartbeat(job_id, worker_id)` — ส่งสัญญาณทำงานต่อเนื่อง
   - `CALL ocr_complete_job(job_id, worker_id, result_json, extracted_meta)` — ส่งผลลัพธ์ข้อความ OCR
   - `CALL ocr_fail_job(job_id, worker_id, error_message, can_retry)` — แจ้งกรณีประมวลผลล้มเหลว
2. **มาตรฐานการเชื่อมต่อ:**
   - บังคับใช้ TLS พร้อมตรวจ CA (`mysql-ca.pem`) และตรวจ Hostname
   - บังคับใช้ Encoding `utf8mb4` และ Timezone `UTC`
   - **ต้องปิดและเคลียร์ Result sets ทุกครั้ง:** ใช้ `while cursor.nextset(): pass` เสมอ
3. **การตรวจสอบไฟล์ (Integrity):**
   - ตรวจสอบ SHA-256 Hash ของไฟล์ PDF เทียบกับค่าในคิวงานก่อนเริ่มประมวลผล OCR เสมอ

---

## 4. ข้อตกลงการพัฒนาและการ Push ขึ้น Git (Workflow Conventions)

- **นับรอบการอัปเดต:** ทำการ Commit และ Push ขึ้น GitHub ทุกๆ 3 รอบการแก้ไข หรือเมื่อผู้ใช้สั่งโดยตรง
- **การตั้งชื่อ Commit:** ใช้รูปแบบ Conventional Commits เช่น `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`
