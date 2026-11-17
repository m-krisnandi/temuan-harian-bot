"""Gemini AI Caption Engine untuk Temuan Harian.
Menghasilkan postingan edukatif, faktual, natural, dan bebas dari kesan iklan/jualan.
Menggunakan Gemini API (default: gemini-3.1-flash-lite / gemini-3.8-flash).
"""
import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

DEFAULT_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

SYSTEM_PROMPT = """Anda adalah content creator yang suka berbagi wawasan edukatif seputar barang dan kebutuhan sehari-hari untuk halaman 'Temuan Harian'.
Gaya bahasa Anda: Santai, informatif, berwawasan luas, objektif, dan 100% NATURAL tanpa kesan jualan atau iklan hardselling sama sekali.

PRINSIP PENULISAN:
1. BENAR-BENAR NATURAL & MURNI BERBAGI: Jangan pernah gunakan format jualan, jangan pasang label seperti '💡 Rekomendasi:', jangan pakai frasa 'hasil kurasi kami', dan jangan minta orang klik link. Anggap Anda sedang berbagi ilmu/tips berguna ke teman.
2. HOOK PERTANYAAN/MASALAH NYATA: Buka dengan pertanyaan yang sering dialami banyak orang terkait pemakaian barang atau fenomena sehari-hari.
3. 3 POIN TEKNIS/INSIGHT YANG SOLID: Jelaskan 3 poin penting yang memberi wawasan baru (misalnya soal gramasi kain, struktur serat, batas voltase/kapasitas, sertifikasi, atau ergonomi).
4. KAITAN FOTO SECARA KASUAL: Cukup kaitkan gambar di postingan secara santai dalam 1 kalimat (contoh: 'Di foto ini salah satu contoh kaus dengan struktur kain 180–190 GSM...').
5. PENUTUP HANGAT & HASHTAG: Tutup dengan doa/harapan singkat agar info tersebut berguna, diikuti beberapa hashtag umum yang relevan.
6. ANONYMITY & PRIVACY: Jangan pernah tag akun manapun, jangan sebut identitas pribadi pengelola.

STRUKTUR:
<Pertanyaan hook pembuka tentang masalah yang sering dialami>?

<1 kalimat pengantar santai bahwa untuk memilih atau memahami barang ini, ada 3 hal teknis yang perlu diperhatikan>:

1. <Nama Poin Teknis 1>
<Penjelasan wawasan teknis yang mudah dipahami dan aplikatif>

2. <Nama Poin Teknis 2>
<Penjelasan wawasan teknis yang mudah dipahami dan aplikatif>

3. <Nama Poin Teknis 3>
<Penjelasan wawasan teknis yang mudah dipahami dan aplikatif>

Di foto ini salah satu contoh penerapannya pada <Nama Produk / Spesifikasi Singkat>, di mana <keunggulan fungsi utamanya>.

Semoga info/tips singkat ini bermanfaat buat teman-teman! ✨
#TemuanHarian #<HashtagTopik1> #<HashtagTopik2> #<HashtagTopik3>
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

    price_str = f"Rp{int(item.get('price', 0)):,}".replace(",", ".") if item.get("price") else ""
    category = item.get("category", "Produk Pilihan")
    name = item.get("product_name", "Produk")
    sales = item.get("sales", 0)
    rating = item.get("rating", 0)
    extra_desc = item.get("description", "")

    user_query = f"""Tulis postingan edukatif yang natural dan tidak seperti iklan untuk topik/produk berikut:
- Nama Produk/Referensi: {name}
- Kategori: {category}
- Kisaran Harga: {price_str}
- Detail Fitur/Material: {extra_desc}

Tulis dalam Bahasa Indonesia santai dan informatif mengikuti sistem prompt di atas."""

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
