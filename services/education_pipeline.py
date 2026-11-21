"""Pipeline Pembuatan Konten Edukasi Murni Otomatis (5-Stage Content Engine).

Tahapan Pipeline Lengkap:
[Riset Fakta Terkini]       -> last30days (isu nyata, perdebatan & keluhan terkini pengguna dari forum/lapangan)
           ↓
[Struktur & Format Riset]   -> blog (template news-analysis / problem breakdown / comparison + sitasi sumber)
           ↓
[Hook & Daya Tarik Tulisan] -> copywriting (headline memikat langsung to-the-point, orientasi manfaat pembaca)
           ↓
[Penyaringan Gaya Bahasa]   -> humanizer (100% bebas 'Pernah nggak sih...', tanpa emoji, gaya pakar santai)
           ↓
[Kurasi Visual Manusia]     -> stock_photos (Unsplash/Pexels foto fotografer manusia nyata, aman dari penalti AI Meta)
"""

import os
import json
import time
import random
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple

from services.gemini_client import DEFAULT_GEMINI_KEY, DEFAULT_MODEL, strip_emojis
from services.stock_photos import get_stock_service

WIB = timezone(timedelta(hours=7))

# Bank Topik Riset Berdasarkan Isu & Kebutuhan Nyata Sehari-hari (Prinsip last30days & Recency)
RESEARCH_TOPIC_BANK = [
    {
        "topic": "Alasan cuci mobil atau motor saat mesin masih panas bikin cat cepat kusam dan memicu jamur air",
        "category": "Otomotif & Kendaraan",
        "visual_query": "car engine wash detailing",
        "default_source": "Kajian Komparasi Termal Cat Otomotif & Detailing Lapangan"
    },
    {
        "topic": "Bahaya kabel charger tipis di colokan mobil: kenapa arus listrik sering drop dan baterai HP panas",
        "category": "Elektronik & Gadget",
        "visual_query": "car charger phone dashboard",
        "default_source": "Pengujian Resistansi Konduktor Tembaga & Standar USB Power Delivery"
    },
    {
        "topic": "Beda katun combed 24s vs 30s di cuaca lembap tropis: kenapa bahan terlalu tebal malah bikin gerah dan bau apek",
        "category": "Pakaian Pria",
        "visual_query": "cotton fabric t shirt texture",
        "default_source": "Uji Kerapatan Serat Tekstil (GSM) & Daya Serap Sirkulasi Udara"
    },
    {
        "topic": "Kunci busa salju tebal saat cuci kendaraan ada di rasio air dan nozzle sprayer, bukan di banyaknya sampo",
        "category": "Otomotif & Kendaraan",
        "visual_query": "car wash foam snow lance",
        "default_source": "Eksperimen Detailing Otomotif Mandiri & Tekanan Udara Sprayer"
    },
    {
        "topic": "Trik menyimpan sambal botol kemasan tanpa bahan pengawet agar tahan berminggu-minggu tanpa basi",
        "category": "Makanan & Minuman",
        "visual_query": "chili sambal bottle jar cooking",
        "default_source": "Pedoman Higienitas Pangan & Stabilitas Asam Lemak Minyak Alami"
    },
    {
        "topic": "Kesalahan fatal pakai mata bor besi untuk dinding bata yang bikin lubang melebar dan fisher longgar",
        "category": "Rumah Tangga & Dekorasi",
        "visual_query": "power drill concrete wall fixing",
        "default_source": "Panduan Standar Perkakas Konstruksi Ringan & Dynabolt Fisher"
    },
    {
        "topic": "Kenapa charger watt besar tetap aman dipakai untuk HP dengan kapasitas baterai kecil",
        "category": "Elektronik & Gadget",
        "visual_query": "fast charging phone adapter desk",
        "default_source": "Spesifikasi Konsorsium Protokol Komunikasi Daya USB-IF"
    },
    {
        "topic": "Jebakan potongan kaos oversized: beda potongan drop-shoulder proporsional vs salah ukuran yang kelihatan kedodoran",
        "category": "Pakaian Pria",
        "visual_query": "oversized t shirt streetwear modern",
        "default_source": "Analisis Pola Potongan Busana Pria & Proporsi Garis Bahu"
    },
    {
        "topic": "Trik merawat wajan anti-lengket teflon atau granit agar lapisan coating tidak mudah mengelupas dan rusak",
        "category": "Rumah Tangga & Dekorasi",
        "visual_query": "non stick frying pan cooking stove",
        "default_source": "Panduan Perawatan Lapangan Peralatan Dapur & Batas Termal PTFE"
    },
    {
        "topic": "Ciri khas aki motor atau mobil mulai tekor sebelum mogok total di tengah jalan",
        "category": "Otomotif & Kendaraan",
        "visual_query": "car battery mechanic testing voltage",
        "default_source": "Data Uji Voltmeter Tegangan Beban Starter Kendaraan Bermotor"
    },
    {
        "topic": "Alasan kipas portable motor brushless lebih awet dan tidak cepat panas dibanding motor dinamo biasa",
        "category": "Elektronik & Gadget",
        "visual_query": "portable fan modern minimalist desk",
        "default_source": "Kajian Efisiensi Motor Brushless DC & Disipasi Panas Baterai"
    },
    {
        "topic": "Cara ventilasi silang sederhana agar kamar tidur tidak lembap, pengap, dan bebas dari bau apek",
        "category": "Rumah Tangga & Dekorasi",
        "visual_query": "clean bedroom window sunlight morning",
        "default_source": "Prinsip Sirkulasi Udara Pasif & Pengukuran Kelembapan Relatif (RH)"
    }
]

# 1. Prompt Sistem Pipeline 5-Tahap Terintegrasi
PIPELINE_SYSTEM_PROMPT = """Anda adalah Senior Content Researcher & Editor untuk halaman 'Temuan Harian'.
Tugas Anda adalah menulis konten EDUKASI MURNI yang bermutu tinggi, berwawasan mendalam, dan 100% HUMAN.

ATURAN PIPELINE WAJIB (5 TAHAP):
1. RISET FAKTA & ISU TERKINI (Prinsip last30days):
   - Angkat perdebatan nyata, keluhan umum, atau salah kaprah yang sering dialami orang di kehidupan sehari-hari.
   - Jangan menyajikan teori abstrak kampus. Sajikan fakta teknis praktis yang dirasakan langsung di lapangan.

2. STRUKTUR ANALISIS (Prinsip blog / news-analysis):
   - Pola: [Observasi Langsung / Koreksi Mitos] -> [Penjelasan Mekanisme Teknis Sebab-Akibat] -> [Aturan Praktis yang Mudah Diterapkan] -> [Sitasi Sumber Riset].
   - Kalimat pendek-pendek (1-2 baris). Spasi lega antar paragraf agar enak dibaca cepat (skimming) di layar smartphone.

3. HOOK MEMIKAT (Prinsip copywriting):
   - Buka langsung di inti masalah (in media res).
   - DILARANG KERAS membuka dengan pertanyaan klise template AI:
     * DILARANG: 'Pernah nggak sih...', 'Pernahkah Anda...', 'Sering kesel nggak sih...', 'Tahukah kamu...', 'Apakah Anda tahu...'.
   - Mulailah dengan observasi tegas atau bantahan mitos (Contoh: 'Busa tebal pas cuci mobil kuncinya bukan di banyak sampo...', 'Banyak yang ngira bahan kaos makin tebal makin bagus...').

4. PENYARINGAN GAYA BAHASA (Prinsip humanizer):
   - Hapus semua gaya bahasa bot/sales AI.
   - DILARANG penutup klise: 'Semoga tips ini membantu...', 'Semoga bermanfaat...', 'Semoga ngebantu...'.
   - Akhiri secara natural dengan kesimpulan praktis.
   - TANPA EMOJI: DILARANG menggunakan emotikon/emoji apapun. Hanya teks bersih dan tanda baca standar.
   - NON-KOMERSIAL: DILARANG menyebut nama merek produk belanja, DILARANG link Shopee, DILARANG kata 'beli', 'checkout', atau 'rekomendasi toko'. Ini konten edukasi murni.

5. SITASI SUMBER RISET (Wajib Disertakan):
   - Wajib cantumkan 1 baris sumber rujukan/data riset di bagian paling bawah sebelum hashtag.
   - Format: 'Sumber riset: <Nama Referensi / Kajian / Forum / Standar Teknis>'

FORMAT OUTPUT:
[Judul Ringkas Topik Edukasi]

[Paragraf Hook Langsung ke Fakta Nyata / Koreksi Mitos]

[Paragraf Pembahasan Mekanisme Sebab-Akibat]

[Paragraf Solusi / Aturan Praktis yang Mudah Dipraktikkan]

Sumber riset: <Rujukan / Sumber Fakta Terkait>

#TemuanHarian #<Hashtag1> #<Hashtag2> #<Hashtag3>
"""


def generate_educational_article(
    topic: str,
    category: str = "Wawasan Harian",
    context_notes: str = "",
    default_source: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """Menjalankan 5-Stage Pipeline via Gemini AI untuk menghasilkan artikel edukasi murni lengkap dengan sitasi sumber."""
    key = api_key or os.getenv("GEMINI_API_KEY", "") or DEFAULT_GEMINI_KEY
    if not key:
        return None

    selected_model = model or os.getenv("GEMINI_MODEL", "") or DEFAULT_MODEL

    source_hint = f"\nRekomendasi sumber rujukan untuk dicantumkan: {default_source}" if default_source else ""

    user_query = f"""Rancang konten edukasi murni mengikuti 5-Stage Pipeline (last30days + blog + copywriting + humanizer + source citation).
Topik Pembahasan: {topic}
Kategori: {category}
Catatan Konteks: {context_notes}{source_hint}

PENTING:
- DILARANG keras pembuka klise ('Pernah nggak sih...', 'Sering kesel...').
- DILARANG penutup klise ('Semoga bermanfaat...').
- DILARANG emoji sama sekali.
- WAJIB sertakan baris 'Sumber riset: ...' di bagian akhir sebelum hashtag.
- Non-komersial: tanpa link shopee dan tanpa ajakan beli."""

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{PIPELINE_SYSTEM_PROMPT}\n\n{user_query}"}]
            }
        ],
        "generationConfig": {
            "temperature": 0.75,
            "maxOutputTokens": 1000
        }
    }

    candidate_models = [selected_model, "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash"]
    for m in candidate_models:
        if not m:
            continue
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts and "text" in parts[0]:
                        raw_text = parts[0]["text"].strip()
                        clean_text = strip_emojis(raw_text)

                        lines = [l.strip() for l in clean_text.split("\n") if l.strip()]
                        title = lines[0] if lines else topic
                        if title.startswith("#"):
                            title = title.lstrip("#").strip()

                        # Pastikan ada baris sumber riset
                        if "sumber riset" not in clean_text.lower() and default_source:
                            clean_text = clean_text.replace(
                                "#TemuanHarian",
                                f"Sumber riset: {default_source}.\n\n#TemuanHarian"
                            )

                        return {
                            "title": title,
                            "content": clean_text,
                            "category": category
                        }
        except Exception:
            continue

    return None


def fetch_educational_visual(query: str, db=None) -> str:
    """Mengambil stok foto fotografer manusia bebas AI dari Unsplash/Pexels."""
    stock = get_stock_service(db=db)
    try:
        photos = stock.search(query, db=db)
        if photos:
            return photos[0]["url"]
    except Exception:
        pass
    return "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=1080&q=80"


class EducationContentService:
    """Service terpadu untuk membuat, menjadwalkan, dan me-replenish konten edukasi murni otomatis."""

    def __init__(self, db):
        self.db = db

    def create_and_queue(
        self,
        topic: str,
        category: str,
        search_query_visual: str,
        scheduled_at: str,
        default_source: str = ""
    ) -> Dict[str, Any]:
        """Menghasilkan artikel edukasi murni dan menyimpannya ke antrean."""
        article = generate_educational_article(
            topic=topic,
            category=category,
            default_source=default_source
        )
        if not article:
            raise RuntimeError("Gagal menghasilkan artikel edukasi dari Gemini API.")

        image_url = fetch_educational_visual(search_query_visual or topic, db=self.db)
        item_id = f"edu_{int(time.time())}_{random.randint(100, 999)}"

        item_data = {
            "item_id": item_id,
            "product_name": article["title"],
            "product_url": "",
            "affiliate_link": "",
            "image_url": image_url,
            "price": 0,
            "discount_rate": 0,
            "rating": 5.0,
            "sales": 0,
            "commission_rate": 0,
            "caption": article["content"],
            "category": category,
            "status": "APPROVED",
            "platform": "FACEBOOK",
            "tiktok_link": "",
            "scheduled_at": scheduled_at,
            "media_type": "IMAGE",
            "video_url": "",
            "market_score": 95.0,
            "commission_amount": 0.0,
            "shop_name": "Temuan Harian Riset",
            "rejection_reason": "",
            "post_type": "EDUCATION"
        }

        self.db.insert_product(item_data)
        self.db.update_schedule(item_id, scheduled_at)
        self.db.update_post_type(item_id, "EDUCATION")

        return item_data

    def auto_replenish(self, days_ahead: int = 3) -> List[Dict[str, Any]]:
        """Otomatis memeriksa dan mengisi slot jam edukasi (07:30 & 17:00) yang masih kosong."""
        now_wib = datetime.now(WIB)
        edu_slots = [(7, 30), (17, 0)]  # Slot Waktu Edukasi Murni

        # Ambil daftar seluruh jadwal terdaftar
        scheduled_list = self.db.list_scheduled(limit=100)
        existing_schedules = {it.get("scheduled_at", "") for it in scheduled_list}

        # Kumpulkan judul yang sudah ada agar tidak duplikat topik
        existing_titles = {it.get("product_name", "").lower() for it in scheduled_list}

        created_items = []
        topic_pool = list(RESEARCH_TOPIC_BANK)
        random.shuffle(topic_pool)
        topic_idx = 0

        # Cek slot kosong dalam rentang days_ahead
        for d in range(days_ahead):
            target_date = now_wib.date() + timedelta(days=d)
            for hour, minute in edu_slots:
                slot_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=WIB)
                
                # Jangan isi slot yang sudah lewat waktu sekarang + buffer 15 menit
                if slot_dt <= now_wib + timedelta(minutes=15):
                    continue

                slot_str = slot_dt.strftime("%Y-%m-%d %H:%M")
                if slot_str not in existing_schedules:
                    # Slot edukasi kosong ditemukan! Buat konten otomatis via pipeline
                    if topic_idx < len(topic_pool):
                        entry = topic_pool[topic_idx]
                        topic_idx += 1
                    else:
                        entry = random.choice(RESEARCH_TOPIC_BANK)

                    try:
                        print(f"[EDU-AUTO-SCHEDULER] Menghasilkan konten edukasi otomatis untuk slot: {slot_str} ({entry['topic'][:35]}...)")
                        item = self.create_and_queue(
                            topic=entry["topic"],
                            category=entry["category"],
                            search_query_visual=entry["visual_query"],
                            scheduled_at=slot_str,
                            default_source=entry.get("default_source", "")
                        )
                        existing_schedules.add(slot_str)
                        created_items.append(item)
                        time.sleep(1.5)  # Beri jeda antar panggilan API
                    except Exception as e:
                        print(f"[EDU-AUTO-SCHEDULER ERROR] Gagal untuk slot {slot_str}: {e}")

        return created_items
