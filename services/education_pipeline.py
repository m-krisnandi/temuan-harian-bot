"""Pipeline Pembuatan Konten Edukasi Murni (4-Stage Content Engine).

Tahapan Pipeline:
[Riset Fakta Terkini]       -> last30days (data/isu nyata, perdebatan & keluhan terkini pengguna)
           ↓
[Struktur & Format Riset]   -> blog (template news-analysis / problem breakdown / comparison)
           ↓
[Hook & Daya Tarik Tulisan] -> copywriting (headline memikat, fokus orientasi pembaca, anti-klise)
           ↓
[Penyaringan Gaya Bahasa]   -> humanizer (bersihkan kalimat kaku, hilangkan AI-clichés, 100% natural tanpa emoji)
           ↓
[Kurasi Visual Manusia]     -> stock_photos (Unsplash/Pexels foto fotografer manusia nyata, aman dari penalti AI Meta)
"""

import os
import json
import time
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, List

from services.gemini_client import DEFAULT_GEMINI_KEY, DEFAULT_MODEL, strip_emojis
from services.stock_photos import get_stock_service


# 1. Prompt Sistem Pipeline 4-Stage
PIPELINE_SYSTEM_PROMPT = """Anda adalah Senior Content Researcher & Editor untuk halaman 'Temuan Harian'.
Tugas Anda adalah menulis konten EDUKASI MURNI yang bermutu tinggi, berwawasan mendalam, dan 100% HUMAN.

ATURAN PIPELINE WAJIB (4 TAHAP):
1. RISET FAKTA & ISU TERKINI (Prinsip last30days):
   - Angkat perdebatan nyata, keluhan umum, atau salah kaprah yang sering dialami orang di kehidupan sehari-hari.
   - Jangan menyajikan teori abstrak kampus. Sajikan fakta teknis praktis yang dirasakan langsung di lapangan.

2. STRUKTUR ANALISIS (Prinsip blog / news-analysis):
   - Pola: [Observasi Langsung / Koreksi Mitos] -> [Penjelasan Mekanisme Nyata] -> [Aturan Praktis yang Mudah Diterapkan].
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

FORMAT OUTPUT:
[Judul Ringkas Topik Edukasi]

[Paragraf Hook Langsung ke Fakta Nyata]

[Paragraf Pembahasan Mekanisme]

[Paragraf Solusi / Aturan Praktis]

#TemuanHarian #<Hashtag1> #<Hashtag2> #<Hashtag3>
"""


def generate_educational_article(
    topic: str,
    category: str = "Wawasan Harian",
    context_notes: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """Menjalankan 4-Stage Pipeline via Gemini AI untuk menghasilkan artikel edukasi murni."""
    key = api_key or os.getenv("GEMINI_API_KEY", "") or DEFAULT_GEMINI_KEY
    if not key:
        return None

    selected_model = model or os.getenv("GEMINI_MODEL", "") or DEFAULT_MODEL

    user_query = f"""Rancang konten edukasi murni mengikuti 4-Stage Pipeline (last30days + blog + copywriting + humanizer).
Topik Pembahasan: {topic}
Kategori: {category}
Catatan Konteks Tambahan: {context_notes}

Ingat: Dilarang pembuka klise ('Pernah nggak sih'), dilarang penutup klise, dilarang emoji, dan jangan ada ajakan belanja/iklan produk."""

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
    photos = stock.search(query, per_page=5)
    if photos:
        return photos[0]["url"]
    return "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=1080&q=80"


class EducationContentService:
    """Service terpadu untuk membuat dan memasukkan postingan edukasi murni ke antrean."""

    def __init__(self, db):
        self.db = db

    def create_and_queue(
        self,
        topic: str,
        category: str,
        search_query_visual: str,
        scheduled_at: str
    ) -> Dict[str, Any]:
        """Menghasilkan artikel edukasi murni dan menyimpannya ke antrean."""
        article = generate_educational_article(topic=topic, category=category)
        if not article:
            raise RuntimeError("Gagal menghasilkan artikel edukasi dari Gemini API.")

        image_url = fetch_educational_visual(search_query_visual or topic, db=self.db)
        item_id = f"edu_{int(time.time())}"

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
            "market_score": 90.0,
            "commission_amount": 0.0,
            "shop_name": "Temuan Harian Editorial",
            "rejection_reason": "",
            "post_type": "EDUCATION"
        }

        self.db.insert(item_data)
        self.db.update_schedule(item_id, scheduled_at)
        self.db.update_post_type(item_id, "EDUCATION")

        return item_data
