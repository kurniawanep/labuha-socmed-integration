# Panduan Deployment Docker (Production Server)

Panduan ini berisi langkah-langkah untuk menjalankan **Bot Diseminasi WhatsApp (Labuha SocMed Integration)** menggunakan Docker & Docker Compose di server produksi (Linux/Ubuntu/VPS).

---

## 📁 File Docker yang Disediakan

1. **`Dockerfile`**: Image berbasis `python:3.11-slim` lengkap dengan package sistem (`libmagic1`, `ffmpeg`, `sqlite3`, `ca-certificates`, `tzdata`).
2. **`docker-compose.yml`**: Konfigurasi container service dengan *volume mount* otomatis untuk menjaga sesi WhatsApp (`session.sqlite3`), log (`bot.log`), dan file download (`downloads/`).
3. **`requirements.txt`**: Daftar dependency Python yang sudah disesuaikan untuk lingkungan Linux/Docker.
4. **`.dockerignore`**: Mengabaikan file temporary/cache/virtualenv lokal saat proses build image.
5. **`.env.example`**: Template variabel lingkungan.

---

## 🚀 Langkah Deploy di Server Production

### 1. Prasyarat Server
Pastikan server produksi Anda sudah terinstall Docker dan Docker Compose.
```bash
docker --version
docker compose version
```

### 2. Copy/Clone Project ke Server
Upload seluruh folder project ke server produksi Anda.

### 3. Persiapan File Konfigurasi & Sesi WhatsApp
Di folder project di server:
- Pastikan file `.env` sudah terisi dengan kredensial Supabase, Meta Page ID, IG ID, Threads Token, serta JID WhatsApp Target.
- **PENTING (Transfer Sesi WhatsApp)**: Jika bot WhatsApp sudah terhubung di komputer lokal Anda, cukup copy file **`session.sqlite3`** ke folder project di server! Dengan begini, Anda **tidak perlu scan QR code ulang** di server.

### 4. Build dan Jalankan Container
Jalankan perintah berikut di terminal server:

```bash
docker compose up -d --build
```

Container akan berjalan di background (`-d`).

---

## 📊 Perintah Manajemen & Monitoring Container

### A. Melihat Logs (Cek Status / Scan QR Code)
Jika `session.sqlite3` belum ada dan perlu scan QR Code pertama kali, lihat log secara realtime:
```bash
docker compose logs -f whatsapp-bot
```

### B. Cek Status Container
```bash
docker compose ps
```

### C. Menghentikan Bot
```bash
docker compose down
```

### D. Restart Bot
```bash
docker compose restart whatsapp-bot
```

### E. Rebuild Container (Jika ada perubahan kode)
```bash
docker compose up -d --build
```

---

## 🛠️ Menjalankan Script Helper di Dalam Container

### 1. Menjalankan Generator Rekap (`report_generator.py`)
Anda bisa menjalankan script rekap langsung di dalam container Docker:
```bash
# Rekap semua data
docker compose exec whatsapp-bot python report_generator.py

# Rekap rentang tanggal tertentu
docker compose exec whatsapp-bot python report_generator.py --from 2026-07-01 --to 2026-07-31

# Rekap detail
docker compose exec whatsapp-bot python report_generator.py --detail
```

### 2. Memperbarui Token Threads (`exchange_threads_token.py`)
```bash
docker compose exec -it whatsapp-bot python exchange_threads_token.py
```

---

## 🔒 Catatan Keamanan & Persistence Volume

File/Folder berikut secara otomatis dipasang (*volume mount*) dari server host ke dalam container:
- `session.sqlite3` : Menjaga login WhatsApp agar tidak terputus saat container di-restart.
- `downloads/` : Menyimpan media temporary.
- `bot.log` : Menyelamatkan file log aplikasi.
- `staff.json` : Database daftar staf lokal.
- `channel_messages.json` : Cache pesan channel.
