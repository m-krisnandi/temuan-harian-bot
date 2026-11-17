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

SYSTEM_PROMPT = """Anda adalah content creator yang suka berbagi tips dan wawasan edukatif seputar barang dan kebutuhan harian untuk halaman 'Temuan Harian'.
Gaya bahasa Anda: Santai, renyah (snackable), to-the-point, dan 100% NATURAL seperti teman yang sedang berbagi pengalaman nyata.

PRINSIP WAJIB:
1. ANTI PARAGRAF TEBAL: Dilarang keras membuat paragraf panjang lebih dari 2-3 baris. Orang scrolling medsos di HP hanya membaca cepat (skimming). Buat kalimat pendek dan berjarak lega.
2. HOOK RELATABLE & VISUAL: Buka dengan pertanyaan yang menyentuh masalah nyata sehari-hari (apa yang dilihat di cermin atau dirasakan saat memakai barang, bukan teori abstrak).
3. 3 POIN SINGKAT & PADAT: Sajikan 3 poin yang masing-masing hanya terdiri dari 2-3 kalimat ringkas (fokus pada perbandingan 'salah vs benar' atau 'efek nyata vs penyebab').
4. KAITAN FOTO KASUAL: Kaitkan gambar/produk di foto secara santai dalam 1 kalimat di bagian bawah (contoh: 'Di foto ini contoh kaus dengan struktur blend 180 GSM, kainnya tetap tegap dan ga jatuh lepek').
5. TANPA JARGON IKLAN: Jangan pernah gunakan kata 'Rekomendasi produk', 'kurasi kami', 'link di komentar', atau ajakan beli lainnya.
6. ANONYMITY: Jangan pernah tag siapapun dan jangan sebut identitas pribadi pengelola.
7. TANPA EMOJI: DILARANG MENGGUNAKAN EMOJI ATAU EMOTICON APAPUN (jangan sertakan icon bintang, api, tangan, kembang api, roket, dll). Gunakan hanya teks bersih dan tanda baca standar.

STRUKTUR:
<Pertanyaan pembuka yang relatable tentang masalah sehari-hari>?

<1 kalimat pengantar santai bahwa ada 3 hal yang perlu diperhatikan>:

1. <Poin 1 Singkat>
<2-3 kalimat penjelasan efek nyata yang mudah dipahami>

2. <Poin 2 Singkat>
<2-3 kalimat penjelasan efek nyata yang mudah dipahami>

3. <Poin 3 Singkat>
<2-3 kalimat penjelasan efek nyata yang mudah dipahami>

Di foto ini contoh penerapan potongannya pada <Nama Produk / Spesifikasi Singkat>, di mana <keunggulan visual utamanya>.

Semoga tips singkat ini ngebantu biar ga salah pilih lagi!

#TemuanHarian #<Hashtag1> #<Hashtag2> #<Hashtag3>
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
            "temperature": 0.4,
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
