# Temuan Harian — Multi-Affiliate & Multi-Channel Automation Hub

Sistem otomasi kurasi produk Multi-Affiliate (**Shopee Affiliate & TikTok Shop**) dan Multi-Channel Publishing (**Facebook Page, Threads, dan Instagram**) dengan arsitektur **Clean Code, Prinsip SOLID, dan Dependency Injection (DI)**.

Dilengkapi dengan Web Catalog Publik, Admin Control Center (FastAPI), AI Caption Generator edukatif berbasis Google Gemini 3.8 Flash, serta kesiapan integrasi Meta Marketing API.

---

## 🏗️ Arsitektur SOLID & Dependency Injection

Proyek ini dibangun mengikuti prinsip rekayasa perangkat lunak standar enterprise:

```text
temuan-harian-bot/
├── core/                           # Core Contracts & IoC Container
│   ├── interfaces.py               # Abstract Base Classes (Pure Contracts)
│   └── dependencies.py             # Dependency Injection Factory / Providers
│
├── repositories/                   # Data Persistence Layer (SRP)
│   └── database.py                 # SQLite ConnectionFactory, Product, Settings, Logs Repos
│
├── services/                       # Business Logic Layer
│   ├── captions.py                 # Strategy Pattern: Gemini AI & Halal Template Engine
│   ├── gemini_client.py            # Google Gemini 3.8 Flash Client
│   └── shopee_scraper.py           # 1-Click Shopee Preview & Cover Photo Scraper
│
├── publishers/                     # Social Media Integration Layer (LSP & DIP)
│   ├── dispatcher.py               # Multi-channel broadcaster
│   ├── facebook.py                 # Meta Facebook Page (Graph API v25.0)
│   ├── threads.py                  # Meta Threads API Publisher
│   ├── instagram.py                # Instagram Graph API Publisher
│   └── meta_ads.py                 # Meta Marketing API (Iklan Sandbox & Live)
│
├── crawlers/                       # Automated Web Discovery
│   ├── scout_viral.py              # Viral discovery engine
│   └── shopee_client.py            # Shopee Open API GraphQL Client
│
├── web/                            # Web Presentation Layer (FastAPI)
│   ├── app.py                      # REST Controllers dengan DI via Depends()
│   └── templates/                  # Jinja2 UI (Public Catalog, Admin, Login)
│
├── deploy/                         # VPS & Container Deployment
│   ├── deploy-vps.sh               # 1-Click Automated VPS Deployment
│   ├── nginx-temuan-harian.pdfumi.com.conf # Nginx Reverse Proxy Config
│   └── temuan-web.service          # Systemd Daemon (Opsional)
│
├── tests/                          # Automated Unit Testing
│   └── test_solid_di.py            # Tests SOLID & Mock DI
│
├── Dockerfile                      # Container Build
├── docker-compose.yml              # Container Orchestration
├── pipeline.py                     # CLI Pipeline Entrypoint
├── DEPLOYMENT.md                   # Panduan Lengkap VPS & SSL
└── .env.example                    # Template Konfigurasi Environment
```

### Detail Penerapan Prinsip SOLID:

1. **S — Single Responsibility Principle (SRP):**
   - [`ProductRepository`](file:///Users/user/Documents/ALUESA/SOLIDPACE/temuan-harian-bot/repositories/database.py): Hanya bertanggung jawab atas siklus hidup antrean barang (`PENDING`, `APPROVED`, `POSTED`).
   - [`SettingsRepository`](file:///Users/user/Documents/ALUESA/SOLIDPACE/temuan-harian-bot/repositories/database.py): Mengelola penyimpanan kunci API, token OAuth, dan switch channel.
   - [`ActivityLogRepository`](file:///Users/user/Documents/ALUESA/SOLIDPACE/temuan-harian-bot/repositories/database.py): Menyimpan audit trail dan log kejadian sistem.
   - Tiap publisher terisolasi di filenya sendiri (`facebook.py`, `threads.py`, `instagram.py`, `meta_ads.py`).

2. **O — Open/Closed Principle (OCP):**
   - Menambah media sosial baru (seperti Twitter/X atau Pinterest) cukup dengan membuat class baru yang mengimplementasikan [`ISocialPublisher`](file:///Users/user/Documents/ALUESA/SOLIDPACE/temuan-harian-bot/core/interfaces.py). [`PublisherDispatcher`](file:///Users/user/Documents/ALUESA/SOLIDPACE/temuan-harian-bot/publishers/dispatcher.py) terbuka untuk ekstensi tanpa perlu modifikasi kode di dalamnya.

3. **L — Liskov Substitution Principle (LSP):**
   - Seluruh publisher mengimplementasikan method `publish_photo()` dan `add_comment()` secara konsisten. Dispatcher dapat memperlakukan publisher apapun secara setara tanpa mengetahui detail internalnya.

4. **I — Interface Segregation Principle (ISP):**
   - Interface dipisah sesuai domain: `ISocialPublisher`, `ICaptionGenerator`, `IProductScraper`, `IProductRepository`, `ISettingsRepository`, `IActivityLogRepository`, dan `IAdsManager`. Klien tidak dipaksa mengimplementasikan method yang tidak diperlukannya.

5. **D — Dependency Inversion Principle (DIP):**
   - Modul tingkat tinggi ([`web/app.py`](file:///Users/user/Documents/ALUESA/SOLIDPACE/temuan-harian-bot/web/app.py) dan [`pipeline.py`](file:///Users/user/Documents/ALUESA/SOLIDPACE/temuan-harian-bot/pipeline.py)) tidak bergantung pada implementasi kelas konkret langsung, melainkan bergantung pada interface via Factory di [`core/dependencies.py`](file:///Users/user/Documents/ALUESA/SOLIDPACE/temuan-harian-bot/core/dependencies.py).

---

## 🌟 Fitur Utama

1. **Multi-Affiliate Support:**
   - **Shopee Affiliate:** Otomatis menghasilkan link pelacakan resmi (`an_redir?origin_link=...&affiliate_id=...&sub_id=...`) tanpa bergantung persetujuan Open API.
   - **TikTok Shop:** Dukungan tautan affiliate TikTok Shop.
   - **Both:** Memungkinkan satu barang memiliki dua link rujukan sekaligus.

2. **Multi-Channel Social Publishing:**
   - **Facebook Fanspage:** Posting foto resolusi tinggi ke feed + menyematkan link affiliate di komentar pertama (First Comment) untuk menjaga reach algoritma Meta tetap tinggi.
   - **Threads API:** Integrasi resmi pembuatan container media dan publikasi otomatis.
   - **Instagram Graph API:** Publikasi otomatis ke feed akun profesional / kreator yang terhubung.

3. **AI Educational Caption Engine (Google Gemini 3.8 Flash):**
   - Menghasilkan narasi edukatif, berbasis fakta spesifikasi riil dan tips kegunaan.
   - Menolak klaim palsu/hiperbola (anti-hoaks) dan mematuhi kaidah halal & etis.
   - Format elegan tanpa emoji berlebihan / kekanak-kanakan (Clean typography).

4. **1-Click Auto-Preview Scraper (15 Kategori Resmi Shopee):**
   - Cukup tempel tautan produk Shopee &rarr; sistem otomatis mengekstrak foto cover resolusi tinggi resmi, judul, dan mengklasifikasikan ke dalam kategori resmi Shopee Indonesia.

5. **Meta Marketing API Sandbox Ready:**
   - Mengelola kampanye iklan, set iklan, materi iklan (ad creatives), dan pelacakan performa.

6. **Web Dashboard & REST API:**
   - Antarmuka web modern dengan switch aktif/nonaktif per channel, form kurasi semi-manual, preview foto langsung, dan pengaturan frekuensi tayang harian.

---

## ⚙️ Menjalankan Secara Lokal

### 1. Prasyarat
- Python 3.10+
- Pip & Virtualenv

```bash
# Clone dan buat virtual environment
git clone https://github.com/m-krisnandi/temuan-harian-bot.git
cd temuan-harian-bot
python3 -m venv venv
source venv/bin/activate

# Install dependensi
pip install -r requirements.txt

# Siapkan file environment
cp .env.example .env
```

### 2. Menjalankan Web Dashboard (FastAPI)
```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
```
Buka browser:
- **Katalog Publik:** `http://localhost:8000/`
- **Dashboard Admin:** `http://localhost:8000/admin` (Password default: `temuanharian2026admin`)

### 3. Menjalankan CLI Pipeline
```bash
# Tambah produk kurasi manual dengan Gemini AI
python pipeline.py manual-add \
  --name "Teko Listrik Otomatis 1.5L" \
  --url "https://s.shopee.co.id/xxx" \
  --image "https://down-id.img.susercontent.com/file/id-xxx" \
  --category "Rumah Tangga & Dekorasi" \
  --gemini \
  --approve

# Publikasikan 1 produk siap tayang ke channel aktif
python pipeline.py publish

# Uji coba tanpa posting nyata (dry-run)
python pipeline.py publish --dry-run
```

### 4. Menjalankan Unit Tests
```bash
python3 -m unittest discover tests -v
```

---

## 🚀 Deployment ke Server VPS

Panduan lengkap deployment langkah demi langkah dengan Docker Compose, Nginx Reverse Proxy, dan SSL Certbot dapat dibaca di **[DEPLOYMENT.md](DEPLOYMENT.md)**.

### Perintah Cepat Deployment VPS:
```bash
ssh ubuntu@43.134.26.73
cd /var/www
git clone https://github.com/m-krisnandi/temuan-harian-bot.git
cd temuan-harian-bot
cp .env.production .env
./deploy/deploy-vps.sh
sudo certbot --nginx -d temuan-harian.pdfumi.com
```

---

## 📄 Lisensi
Hak Cipta © 2026 Temuan Harian. Seluruh hak cipta dilindungi undang-undang.
