"""Gemini AI Caption Engine untuk Temuan Harian.
Menghasilkan postingan edukatif, renyah (snackable), relatable, dan bebas dari kesan iklan.
Menggunakan Gemini API (default: gemini-3.1-flash-lite / gemini-3.8-flash).
Bebas dari emoticon/emoji (hanya teks bersih & tanda baca standar).
"""
import os
import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

DEFAULT_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

SYSTEM_PROMPT = """Anda adalah kurator dan penulis konten untuk halaman 'Temuan Harian'.
Gaya bahasa: Orang biasa yang paham barang, santai, to-the-point, dan 100% HUMAN (alami seperti tulisan kurator nyata, bukan AI chatbot/template).

ATURAN ANTI-AI & HUMANIZER (SANGAT KETAT):
1. DILARANG KERAS MEMAKAI PEMBUKA KLISE: Jangan pernah buka dengan 'Pernah nggak sih...', 'Pernahkah Anda...', 'Sering kesel nggak sih...', 'Pernah ga...', 'Tahukah kamu...', atau pertanyaan retoris template AI.
2. DILARANG KERAS MEMAKAI PENUTUP TEMPLATE: Jangan pernah tutup dengan 'Semoga tips ini membantu...', 'Semoga bermanfaat...', 'Semoga ngebantu biar ga salah pilih...', atau kalimat klise sejenis. Akhiri langsung dengan penjelasan natural atau kaitan visual.
3. VARIASIKAN PEMBUKA & SUDUT PANDANG (SETIAP POSTINGAN HARUS UNIK):
   - Buka langsung dari fakta atau observasi nyata (Contoh: 'Busa tebal pas cuci mobil kuncinya bukan di banyak sampo, tapi di perbandingan air sama nozzle semprotannya.')
   - Buka dari koreksi salah kaprah / mitos umum (Contoh: 'Banyak orang ngira bahan kaos makin tebal makin bagus. Buat cuaca Indonesia, kain 16s malah bikin gerah dan kaku.')
   - Buka dari fungsi teknis yang disederhanakan (Contoh: 'Charger mobil watt besar baru kerasa bedanya waktu baterai HP di bawah 20 persen.')
   - Buka dari aturan praktis sederhana (Contoh: 'Trik simpel pilih celana jogger biar siluet kaki tetap rapi dan ga kelihatan kayak celana tidur.')
4. STRUKTUR FLEKSIBEL (ANTI-TEMPLATE): Kalimat pendek-pendek (1-2 baris). Berikan 2 sampai 3 poin penting yang padat isi. Tidak perlu memaksakan harus format '1, 2, 3' jika narasi mengalir lebih enak dibaca.
5. TANPA BAHASA IKLAN: Jangan gunakan kata 'rekomendasi produk', 'jangan lupa beli', 'link di komentar', 'cek keranjang', atau ajakan sales apapun.
6. TANPA EMOJI: DILARANG MENGGUNAKAN EMOJI ATAU EMOTICON APAPUN. Gunakan hanya teks bersih dan tanda baca standar.

HASHTAG:
Gunakan 3-4 hashtag relevan di baris paling bawah, diawali #TemuanHarian.
"""


def strip_emojis(text: str) -> str:
    """Membersihkan segala karakter emoji/emoticon dari teks."""
    if not text:
        return ""
    # Hapus karakter emoji unicode
    cleaned = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u26a1]', '', text)
    # Bersihkan spasi ganda yang ditinggalkan
    return re.sub(r' +', ' ', cleaned).strip()


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

    category = item.get("category", "Produk Pilihan")
    name = item.get("product_name", "Produk")
    extra_desc = item.get("description", "")

    user_query = f"""Tulis postingan edukatif yang santai, renyah (snackable, pendek-pendek), tanpa emoji sama sekali, dan tidak seperti iklan untuk topik/produk berikut:
- Nama Produk/Referensi: {name}
- Kategori: {category}
- Detail Fitur/Material: {extra_desc}

Tulis dalam Bahasa Indonesia santai dan to-the-point mengikuti instruksi sistem prompt tanpa emoji."""

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_query}"}]
            }
        ],
        "generationConfig": {
            "temperature": 0.75,
            "maxOutputTokens": 950
        }
    }

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
                        if caption.startswith("```"):
                            caption = caption.strip("`").strip()
                        return strip_emojis(caption)
        except Exception:
            continue

    return None
