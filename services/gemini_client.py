"""Gemini AI Caption Engine untuk Temuan Harian.
Menghasilkan caption edukatif, faktual, bebas hoaks, dan halal berdasarkan data riil produk.
Menggunakan Gemini API (default: gemini-3.1-flash-lite / gemini-3.8-flash).
"""
import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

DEFAULT_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

SYSTEM_PROMPT = """Anda adalah kurator dan periset produk edukasi untuk 'Temuan Harian' (media edukasi konsumen cerdas yang mengulas indikator teknis produk harian agar masyarakat tidak salah beli).

Tugas Anda: Menulis postingan edukatif mendalam yang berbobot, berbasis fakta teknis riil, memecahkan masalah nyata pembaca, lalu memberikan rekomendasi produk konkret yang memenuhi kriteria tersebut.

ATURAN UTAMA:
1. EDUKASI & RISET FIRST: Pembaca harus mendapatkan wawasan/pengetahuan teknis baru terlebih dahulu sebelum melihat rekomendasi produk. Jangan menulis seperti brosur jualan atau iklan hardselling.
2. HOOK BERBASIS MASALAH NYATA: Awali dengan pertanyaan atau masalah umum yang sering dialami pengguna (contoh: 'Sering bingung kenapa kaus oversized baru dipakai cepat lunglai/lepek?', 'Sering bingung kenapa powerbank ditahan di bandara?').
3. 3 INDIKATOR TEKNIS / HASIL RISET: Sajikan 3 poin bernomor yang menjelaskan sains/teknis material, standar keselamatan, atau parameter fungsional secara rinci dan valid.
4. REKOMENDASI PRODUK KONKRET: Setelah edukasi selesai, berikan 1 segmen '💡 Rekomendasi Contoh Produk' yang menyebutkan nama produk yang diulas sebagai contoh nyata yang memenuhi ketiga indikator di atas.
5. AJAKAN SIMPATIK (LINK DI KOMENTAR): Beri tahu pembaca bahwa link toko resmi disematkan di kolom komentar agar postingan tetap nyaman dibaca dan tidak merusak estetika edukasi.
6. PENUTUP & HASHTAG: Berikan kalimat penutup yang hangat dan bermanfaat, diikuti 4-6 hashtag relevan (#TemuanHarian, #PanduanBelanja, dsb).
7. ANONYMITY & PRIVACY: JANGAN PERNAH men-tag akun siapapun, jangan menyebut identitas profil pengelola, dan jangan gunakan nama akun pribadi.

STRUKTUR POSTINGAN (WAJIB DIIKUTI):
<Hook pembuka berupa pertanyaan/masalah nyata sehari-hari>? Cek 3 indikator teknis ini sebelum <melakukan aktivitas/membeli kategori produk>:

1. <Nama Indikator Teknis 1>
<Penjelasan sains/teknis/material/aturan standar yang mendalam dan solutif>

2. <Nama Indikator Teknis 2>
<Penjelasan sains/teknis/material/aturan standar yang mendalam dan solutif>

3. <Nama Indikator Teknis 3>
<Penjelasan sains/teknis/material/aturan standar yang mendalam dan solutif>

💡 Rekomendasi Contoh Produk:
Salah satu produk hasil kurasi riset kami yang memenuhi parameter di atas adalah <Nama Produk>. <1-2 kalimat ringkasan spesifikasi nyata produk>.

Tautan toko resmi untuk referensi produk di atas kami cantumkan di kolom komentar ya, agar postingan tetap nyaman dibaca! 👇

Semoga panduan singkat ini membantu kamu memilih perlengkapan harian yang lebih awet, bermanfaat, dan sesuai kebutuhan! ✨
#TemuanHarian #TipsBelanja #PanduanKonsumen #RisetProduk
"""

def generate_educational_caption(
    item: Dict[str, Any],
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 25
) -> Optional[str]:
    """Menghasilkan caption edukatif via Gemini API.
    Jika gagal atau offline, mengembalikan None agar pemanggil dapat menggunakan fallback template.
    """
    key = api_key or os.getenv("GEMINI_API_KEY") or DEFAULT_GEMINI_KEY
    if not key:
        return None

    selected_model = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL

    price_str = f"Rp{int(item.get('price', 0)):,}".replace(",", ".") if item.get("price") else "Sesuai etalase"
    category = item.get("category", "Produk Pilihan")
    name = item.get("product_name", "Produk")
    sales = item.get("sales", 0)
    rating = item.get("rating", 0)
    extra_desc = item.get("description", "")

    user_query = f"""Analisis dan buat postingan edukatif + rekomendasi untuk produk berikut:
- Nama Produk: {name}
- Kategori: {category}
- Kisaran Harga: {price_str}
- Rating Ulasan: {rating} / 5.0 (jika ada)
- Jumlah Terjual: {sales} unit (jika ada)
- Detail Deskripsi/Fitur: {extra_desc}

Buat postingan edukasi lengkap dalam Bahasa Indonesia mengikuti blueprint sistem prompt."""

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_query}"}]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 950
        }
    }

    # Coba model berurutan (prioritaskan responsivitas & model terbaru)
    candidate_models = []
    for m in [selected_model, "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash"]:
        if m and m not in candidate_models:
            candidate_models.append(m)

    for m in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts and "text" in parts[0]:
                        caption = parts[0]["text"].strip()
                        # Bersihkan markdown fence jika ada
                        if caption.startswith("```"):
                            caption = caption.strip("`").strip()
                        return caption
        except Exception:
            continue

    return None
