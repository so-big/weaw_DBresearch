# DBresearch - ระบบจัดเก็บและสืบค้นเอกสารสัญญาและงานวิจัย (Encrypted & OCR System)

> **DBresearch** คือเว็บแอปพลิเคชันสำหรับจัดเก็บเอกสารสัญญาและโครงการวิจัยที่มีความปลอดภัยสูง พร้อมระบบเข้ารหัสข้อมูลทุกไฟล์ (Envelope Encryption ด้วย Google Tink AES-256-GCM) และระบบถอดข้อความภาษาไทย/อังกฤษอัตโนมัติด้วย Tesseract OCR เพื่อให้สามารถค้นหาเนื้อหาภายในเอกสาร PDF ได้อย่างแม่นยำ

---

## 📋 Dockerfile นี้มีไว้ทำอะไร? (Purpose of this Dockerfile)

ไฟล์ `Dockerfile` นี้ถูกออกแบบมาให้เป็น **All-in-One Container Image** ที่พร้อมใช้งานทันที:
1. **Frontend + Backend:** รวบรวมเว็บแอปพลิเคชัน (Svelte 5 + Vite) และ FastAPI Web API ในตัวเดียว
2. **OCR Engine:** ติดตั้งชุดเครื่องมือ Tesseract OCR ภาษาไทย (`tesseract-ocr-tha`) และภาษาอังกฤษ (`tesseract-ocr-eng`)
3. **Database Integration:** รองรับทั้งการต่อฐานข้อมูลภายนอก (PostgreSQL ใน Docker Compose) และการทำงานแบบ Standalone
4. **Auto Provisioning:** จัดการ Master Key (KEK), Database Migration (Alembic) และสร้าง/อัปเดตบัญชีผู้ดูแลระบบ (Admin) จากไฟล์ `root.txt` โดยอัตโนมัติ
5. **Configurable Runtime:** สามารถปรับเปลี่ยน Port, Username และ Password ได้ง่ายดายผ่านตัวแปร (Environment Variables) หรือไฟล์กำหนดค่าในทุกๆ การรัน

---

## 🛠 วิธีติดตั้ง Docker (Docker Installation Guide)

### สำหรับ Windows
1. ติดตั้ง **WSL 2** โดยเปิด PowerShell (Run as Administrator) แล้วพิมพ์:
   ```powershell
   wsl --install
   ```
2. ดาวน์โหลดและติดตั้ง **Docker Desktop for Windows** จากเว็บไซต์ทางการ:
   [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
3. เปิด Docker Desktop เข้าไปที่ **Settings -> General** และเปิดใช้งาน **Use the WSL 2 based engine**

### สำหรับ Linux (Ubuntu / Debian)
```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

---

## 🚀 วิธี Build และสั่งรัน Dockerfile

### 1. การ Build Image
เปิด Terminal / PowerShell ในโฟลเดอร์ของโปรเจกต์ แล้วสั่ง:
```bash
docker build -t dbresearch .
```

### 2. การกำหนด Port, Username, และ Password

#### 📌 กำหนด Username & Password ผ่านไฟล์ `root.txt` (ค่าเริ่มต้น)
ที่โฟลเดอร์ Root ของโปรเจกต์จะมีไฟล์ `root.txt`:
```text
admin
admin123456
```
- **บรรทัดที่ 1:** Username
- **บรรทัดที่ 2:** Password (ความยาวอย่างน้อย 10 ตัวอักษร)

#### 📌 กำหนดผ่านไฟล์กำหนดค่าอื่นๆ (`--root` หรือ `ROOT_FILE`)
- **ผ่าน CLI Flag:**
  ```bash
  docker run -p 8120:8120 -v /path/to/my_credentials.txt:/app/custom.txt dbresearch --root /app/custom.txt
  ```
- **ผ่าน Environment Variable:**
  ```bash
  docker run -p 8120:8120 -e ROOT_FILE=/app/custom.txt -v /path/to/my_credentials.txt:/app/custom.txt dbresearch
  ```

#### 📌 กำหนดผ่าน Environment Variable โดยตรง (GUI หรือ CLI)
- **หากใช้งานผ่าน GUI (Docker Desktop / Portainer):**
  ในหน้าตั้งค่า Container ให้ใส่ค่าในช่องกรอกข้อความ (Textbox) ของ Environment Variables:
  - `PORT`: ใส่เลขพอร์ต เช่น `9000`
  - `ADMIN_USERNAME`: ชื่อผู้ดูแลระบบ เช่น `myadmin`
  - `ADMIN_PASSWORD`: รหัสผ่าน เช่น `StrongPassword123`
- **หากใช้งานผ่าน CLI:**
  ```bash
  docker run -d -p 9000:9000 -e PORT=9000 -e ADMIN_USERNAME=myadmin -e ADMIN_PASSWORD=StrongPassword123 dbresearch
  ```

---

## 🎯 ผลลัพธ์เมื่อ Container เริ่มทำงาน

เมื่อรัน Container เรียบร้อย ระบบจะแสดง URL และ API ใน Console Log ทันที:
```text
======================================================================
          DBresearch System Started Successfully!
======================================================================
  Web URL:      http://localhost:8120
  API Docs URL: http://localhost:8120/api/docs
  Admin User:   admin
  Port:         8120
======================================================================
```
- **เข้าใช้งานหน้าเว็บหลัก:** `http://localhost:<PORT>`
- **เข้าดูเอกสาร API (Swagger UI):** `http://localhost:<PORT>/api/docs`

---

## 🖥 การใช้งานบน Windows ผ่านไฟล์ `.bat` (แยก OCR Server และ Web Server)

สำหรับเครื่องที่ติดตั้งไว้ที่ `E:\wear_DBresearch` สามารถดับเบิลคลิกไฟล์ `.bat` เพื่อควบคุมระบบได้ง่ายๆ:

| ไฟล์ `.bat` | หน้าที่การทำงาน |
|---|---|
| **`1_START_OCR_SERVER.bat`** | **เปิดเซิร์ฟเวอร์ OCR** (Container: `dbresearch-ocr`) พร้อม Database |
| **`2_START_WEB_SERVER.bat`** | **เปิดเว็บจริง** (Container: `dbresearch-web`) และเปิด Browser ให้อัตโนมัติ |
| **`START_ALL.bat`** | **เปิดทั้งหมดตามลำดับ** (เปิด OCR Server ก่อน แล้วค่อยเปิดเว็บจริง) |
| **`STOP_OCR_SERVER.bat`** | **ปิดเฉพาะเซิร์ฟเวอร์ OCR** (ช่วยประหยัด CPU/RAM เมื่องานถอดข้อความเสร็จแล้ว) |
| **`RESTART_OCR_SERVER.bat`** | รีสตาร์ทเซิร์ฟเวอร์ OCR |
| **`STOP_WEB_SERVER.bat`** | ปิดเฉพาะเซิร์ฟเวอร์เว็บ |
| **`RESTART_WEB_SERVER.bat`** | รีสตาร์ทเซิร์ฟเวอร์เว็บ |
| **`STOP_ALL.bat`** | ปิดการทำงานของระบบทั้งหมด |
| **`STATUS.bat`** | แสดงสถานะของ Container ทุกตัว และตรวจสอบ Health Check |
| **`CREATE_ADMIN.bat`** | สร้างบัญชีผู้ดูแลระบบเพิ่มเติมแบบ Interactive |

---

## 🔒 ความปลอดภัยและการเก็บรักษาข้อมูล

- **Master Key (KEK):** อยู่ที่ `secrets/kek.json` ถูกสร้างอัตโนมัติในการรันครั้งแรก จัดเก็บแยกต่างหากจาก Git ห้ามลบไฟล์นี้เนื่องจากเป็นกุญแจหลักในการถอดรหัสเอกสารทั้งหมด
- **ที่เก็บไฟล์เอกสาร (Blobs):** ข้อมูลที่ถูกอัปโหลดจะถูกเก็บที่โฟลเดอร์ `data/blobs` ในรูปแบบไฟล์ Ciphertext ที่เข้ารหัสแล้วเท่านั้น
