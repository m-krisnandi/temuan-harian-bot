"""Gemini AI Caption Engine untuk Temuan Harian.
Menghasilkan caption edukatif, faktual, bebas hoaks, dan halal berdasarkan data riil produk.
Menggunakan Gemini API (default: gemini-3.8-flash).
"""
import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

DEFAULT_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

SYSTEM_PROMPT = """Anda adalah kurator dan periset produk untuk 'Temuan Harian' (katalog kurasi produk fungsional, unik, dan bermanfaat).
Tugas Anda: Menulis caption edukatif yang informatif, menarik, dan 100% berbasis fakta produk riil.

ATURAN KETAT:
1. EDUKATIF & FAKTUAL: Jelaskan fungsi produk, teknologi bahan, masalah yang diselesaikan, dan tips pemakaian/perawatan praktis. JANGAN membuat klaim palsu, hoaks, atau hiperbola berlebihan (hindari kata 'paling murah se-Indonesia', 'ajaib', 'pasti ampuh 100%').
2. HALAL & AMAN: Pastikan sudut pandang produk halal, etis, dan aman digunakan sesuai syariat & norma.
3. FORMAT BERSIH TANPA EMOJI: DILARANG KERAS menggunakan emoji kekanak-kanakan atau berlebihan. Gunakan tipografi rapi, bullet points sederhana (•), dan gaya bahasa profesional, ramah, serta elegan.
4. CALL TO ACTION ELEGAN: Beri tahu pembaca bahwa link toko resmi dapat dicek di komentar pertama (First Comment).
5. ANONYMITY & PRIVACY: JANGAN PERNAH men-tag akun siapapun, jangan menyebut identitas profil pengelola, dan jangan gunakan hashtag nama pribadi.

STRUKTUR CAPTION:
[Temuan Harian: <Kategori atau Judul Singkat>]
<Nama Produk>

<1-2 paragraf pendek menjelaskan fungsi nyata, masalah yang diselesaikan, atau keunggulan teknologi bahannya>

• Teknologi Bahan: <ringkasan spesifikasi/material/GSM>
• Keunggulan Siluet / Fungsi: <penjelasan siluet/manfaat nyata>
• Tips Perawatan: <saran praktis penggunaan atau pencucian>
• Kisaran Harga: <harga/rentang harga>

Informasi ketersediaan dan tautan toko resmi telah kami sematkan di komentar pertama.
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

    user_query = f"""Analisis dan buat caption edukatif untuk produk berikut:
- Nama Produk: {name}
- Kategori: {category}
- Kisaran Harga: {price_str}
- Rating Ulasan: {rating} / 5.0 (jika ada)
- Jumlah Terjual: {sales} unit (jika ada)
- Detail Deskripsi/Fitur: {extra_desc}

Buat caption dalam Bahasa Indonesia sesuai instruksi sistem."""

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_query}"}]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 800
        }
    }

    # Coba model berurutan (prioritaskan responsivitas & model terbaru)
    candidate_models = []
    for m in [selected_model, "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-3.5-flash"]:
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
