# Panduan Lengkap Deployment Temuan Harian ke VPS

Dokumen ini memandu proses deployment sistem otomasi **Temuan Harian** ke server VPS (Ubuntu 22.04 / 24.04 LTS) menggunakan **Docker Compose**, **Nginx Reverse Proxy**, dan **Let's Encrypt SSL (Certbot)**.

---

## 1. Spesifikasi Server & Target Subdomain

| Parameter | Konfigurasi |
|---|---|
| **Subdomain** | `temuan-harian.pdfumi.com` |
| **IP Server VPS** | `43.134.26.73` |
| **User SSH** | `ubuntu` |
| **Port Internal Kontainer** | `8000` |
| **Port Host VPS (Docker)** | `8005` |
| **Direktori Proyek di VPS**| `/var/www/temuan-harian-bot` |

---

## 2. Alur Deployment Otomatis (1-Click Script)

Masuk ke server VPS via terminal:
```bash
ssh ubuntu@43.134.26.73
```

Clone repositori dan jalankan skrip otomatisasi:
```bash
# 1. Masuk ke direktori web
cd /var/www

# 2. Clone repositori
git clone https://github.com/m-krisnandi/temuan-harian-bot.git
cd /var/www/temuan-harian-bot

# 3. Siapkan file .env (salin dari .env.production)
cp .env.production .env

# 4. Jalankan deployment otomatis
chmod +x deploy/deploy-vps.sh
./deploy/deploy-vps.sh
```

Skrip di atas secara otomatis akan:
1. Membaca variabel environment dari `.env`.
2. Melakukan build Docker Image Python 3.11-slim.
3. Menjalankan kontainer `temuan-harian-web` di port 8005 dengan volume database persisten (`temuan_data`).
4. Menyalin konfigurasi Nginx ke `/etc/nginx/sites-available/temuan-harian.pdfumi.com`.
5. Mengaktifkan symlink ke `/etc/nginx/sites-enabled/`.
6. Melakukan uji sintaks `nginx -t` dan reload layanan Nginx.

---

## 3. Pemasangan Sertifikat SSL HTTPS (Certbot)

Karena subdomain `temuan-harian.pdfumi.com` sudah diarahkan (pointing A record) ke `43.134.26.73`, pasang SSL gratis dari Let's Encrypt dengan perintah:

```bash
sudo certbot --nginx -d temuan-harian.pdfumi.com
```

- Jika diminta email, masukkan email admin Anda.
- Setujui Terms of Service.
- Pilih opsi **Redirect (2)** agar seluruh lalu lintas HTTP (port 80) dialihkan otomatis ke HTTPS (port 443).

Verifikasi status SSL:
```bash
sudo certbot certificates
```

---

## 4. Konfigurasi Nginx Reverse Proxy Manual (Referensi)

File konfigurasi berada di `/etc/nginx/sites-available/temuan-harian.pdfumi.com`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name temuan-harian.pdfumi.com;

    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8005;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
```

---

## 5. Menjalankan Cron Job Jadwal Posting Otomatis di VPS

Agar posting ke Facebook Page, Threads, dan Instagram berjalan otomatis di jam-jam prime time Indonesia:
- **Pagi:** 08:00 WIB (01:00 UTC)
- **Siang:** 12:30 WIB (05:30 UTC)
- **Malam:** 19:30 WIB (12:30 UTC)

Buka crontab di VPS:
```bash
crontab -e
```

Tambahkan baris berikut:
```cron
# Jadwal posting Temuan Harian otomatis (WIB = UTC+7)
0 1 * * * docker exec temuan-harian-web python pipeline.py publish >> /var/log/temuan-publish.log 2>&1
30 5 * * * docker exec temuan-harian-web python pipeline.py publish >> /var/log/temuan-publish.log 2>&1
30 12 * * * docker exec temuan-harian-web python pipeline.py publish >> /var/log/temuan-publish.log 2>&1
```

---

## 6. Cara Update / Re-deploy Aplikasi

Jika ada perubahan kode baru di GitHub:

```bash
cd /var/www/temuan-harian-bot
git pull origin main
docker compose down
docker compose up -d --build
docker image prune -f
```

---

## 7. Troubleshooting & Cek Log

- **Cek status kontainer:**
  ```bash
  docker compose ps
  ```
- **Lihat log aplikasi realtime:**
  ```bash
  docker logs -f temuan-harian-web
  ```
- **Uji koneksi port lokal host:**
  ```bash
  curl -I http://127.0.0.1:8005
  ```
- **Cek log Nginx:**
  ```bash
  sudo tail -f /var/log/nginx/error.log
  ```
