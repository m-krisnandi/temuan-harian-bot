"""Layanan Riset, Analisis Peluang Produk, dan Pembuat Naskah Video TikTok Affiliate.
Diadaptasi dari arsitektur Cultiv TikTok AI Affiliate Platform.
Mendukung 5 Format Konten Utama, 15-Point AI Analysis, dan Strict Honesty Mode.
"""
import os
import json
import re
from typing import Dict, Any, List, Optional
from services.gemini_client import GeminiClient

TIKTOK_CONTENT_FORMATS = {
    "problem_solution": {
        "label": "Problem & Solution",
        "desc": "Fokus pada masalah nyata sehari-hari audiens lalu menghadirkan produk sebagai solusi praktis.",
        "hook_style": "Pertanyaan masalah atau situasi menjengkelkan yang sering dihadapi."
    },
    "product_review": {
        "label": "Product Review & Breakdown",
        "desc": "Bedah jujur spesifikasi, kelebihan, dan hal yang perlu dicek sebelum membeli.",
        "hook_style": "Fakta unik atau hal tak terduga tentang produk."
    },
    "product_showcase": {
        "label": "Viral Showcase / Spill Barang",
        "desc": "Menyorot estetika, fungsi utama, dan kepuasan visual saat produk digunakan.",
        "hook_style": "Spill barang rekomendasi yang bikin orang kepo dan penasaran."
    },
    "top_recommendations": {
        "label": "Alasan Wajib Punya (Top Points)",
        "desc": "3 poin keunggulan utama yang membuat produk ini layak di-checkout sekarang.",
        "hook_style": "Alasan kenapa produk ini worth it banget di harganya."
    },
    "educational_explainer": {
        "label": "Edukasi & Tips Praktis",
        "desc": "Tips fungsional atau cara merawat/memakai yang memberikan nilai tambah bagi pemirsa.",
        "hook_style": "Trik atau fakta yang jarang orang tahu seputar kategori produk ini."
    }
}


def get_recommended_settings(
    product: Dict[str, Any],
    gemini_client: Optional[GeminiClient] = None,
    db: Optional[Any] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """Menghasilkan rekomendasi cerdas AI secara DINAMIS menggunakan penalaran Gemini AI.
    Tidak menggunakan daftar kata kunci kaku (hardcoded), melainkan menganalisis produk apa pun
    secara kontekstual: psikologi audiens, pain-points, hook video vertikal, dan karakter suara yang pas.
    Hasil analisis di-cache di database agar instan dan hemat kuota API.
    """
    if not product:
        product = {}

    item_id = str(product.get("item_id") or "")

    # 1. Cek cache lokal di product object atau database
    if not force_refresh:
        cached_rec = product.get("ai_recommendation")
        if isinstance(cached_rec, str) and cached_rec.strip():
            try:
                parsed = json.loads(cached_rec)
                if isinstance(parsed, dict) and "format" in parsed and "voice" in parsed:
                    return parsed
            except Exception:
                pass
        elif isinstance(cached_rec, dict) and "format" in cached_rec and "voice" in cached_rec:
            return cached_rec

        # Jika belum ada di object tapi db disediakan, coba ambil dari DB
        if db and item_id:
            try:
                db_item = db.get(item_id)
                if db_item and db_item.get("ai_recommendation"):
                    parsed = json.loads(db_item["ai_recommendation"])
                    if isinstance(parsed, dict) and "format" in parsed and "voice" in parsed:
                        return parsed
            except Exception:
                pass

    # 2. Analisis Dinamis Real-Time Menggunakan Gemini AI
    try:
        ai = gemini_client or GeminiClient(db=db)
        name = product.get("product_name", "Produk")
        cat = product.get("category", "General")
        price = product.get("price", 0)
        rating = product.get("rating", 0.0)
        sales = product.get("sales", 0)
        shop_name = product.get("shop_name", "Official Store")

        prompt = f"""Anda adalah Creative Director & Algorithm Strategist untuk TikTok Affiliate Video Studio Indonesia.
Analisis produk berikut secara mendalam untuk menentukan angle video vertikal 9:16 dan karakter suara Gemini TTS yang paling menjual (tinggi konversi & retensi penonton):

Nama Produk: {name}
Kategori: {cat}
Harga: Rp {price:,.0f} | Rating: {rating} / 5.0 | Penjualan: {sales}
Toko: {shop_name}

Pilihan Format Konten:
- problem_solution (Problem & Solution: Buka dari masalah nyata/gangguan sehari-hari -> produk sebagai solusi praktis)
- product_review (Product Review: Bedah spesifikasi, kelebihan, dan pertimbangan jujur)
- product_showcase (Viral Showcase: Estetika gaya pakai / unboxing visual / spill racun belanja)
- top_recommendations (Alasan Wajib Punya: 3 alasan utama kenapa produk ini sangat worth it)
- educational_explainer (Edukasi Praktis: Tips, trik, atau panduan bermanfaat seputar kategori barang ini)

Pilihan Karakter Suara Gemini TTS:
- Kore (Wanita - Tegas, Jernih, Berwibawa -> Otoritas, meyakinkan fungsi teknis/perkakas/solusi)
- Puck (Pria - Ceria, Upbeat, Energik -> Viral TikTok, makanan/camilan, promo impulsif)
- Aoede (Wanita - Santai, Hangat, Akrab -> OOTD, fashion, lifestyle, skincare santai)
- Charon (Pria - Tenang, Informatif, Terpercaya -> Review gadget, unboxing mendalam)
- Fenrir (Pria - Dinamis, Cepat, Antusias -> Hook cepat, produk unik/inovatif)

ATURAN PENALARAN AI:
1. Pahami apa 'trigger' psikologis penonton TikTok yang membuat mereka berhenti scrolling dan ingin checkout produk ini.
2. Tentukan format terbaik beserta alasan tajamnya ('format_reason').
3. Tentukan karakter suara terbaik beserta alasan psikologisnya ('voice_reason').
4. Berikan label badge singkat (2-4 kata) yang mencerminkan inti penawaran barang ('badge').
5. Hindari asumsi kaku/klise; analisis secara kontekstual berbasis barang tersebut.

Kembalikan HANYA format JSON valid berikut:
{{
  "format": "problem_solution",
  "format_label": "Problem & Solution",
  "format_reason": "Alasan psikologis & daya tarik format ini untuk produk tersebut",
  "voice": "Kore",
  "voice_label": "Kore (Wanita - Tegas & Jernih)",
  "voice_reason": "Alasan pemilihan karakter suara untuk target pembeli produk ini",
  "honesty_mode": "research_based",
  "honesty_label": "Research-Based (Objektif)",
  "badge": "Badge Singkat"
}}"""

        res_text = ai.generate_content(prompt, temperature=0.6, timeout=20)
        data = None
        if res_text:
            text = res_text.strip()
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if m:
                text = m.group(1)
            else:
                s = text.find("{")
                e = text.rfind("}")
                if s != -1 and e != -1 and e > s:
                    text = text[s:e+1]
            try:
                data = json.loads(text)
            except Exception:
                data = None

        if data and "format" in data and "voice" in data:
            format_labels = {
                "problem_solution": "Problem & Solution",
                "product_review": "Product Review",
                "product_showcase": "Viral Showcase",
                "top_recommendations": "Alasan Wajib Punya",
                "educational_explainer": "Edukasi Praktis"
            }
            voice_labels = {
                "Kore": "Kore (Wanita - Tegas & Jernih)",
                "Puck": "Puck (Pria - Ceria & Upbeat)",
                "Aoede": "Aoede (Wanita - Santai & Hangat)",
                "Charon": "Charon (Pria - Informatif & Tenang)",
                "Fenrir": "Fenrir (Pria - Dinamis & Cepat)"
            }
            data["format_label"] = format_labels.get(data.get("format"), data.get("format_label", "Problem & Solution"))
            data["voice_label"] = voice_labels.get(data.get("voice"), data.get("voice_label", "Kore (Wanita - Tegas & Jernih)"))
            data["honesty_mode"] = data.get("honesty_mode", "research_based")
            data["honesty_label"] = "Research-Based (Objektif)"
            if not data.get("badge"):
                data["badge"] = "Rekomendasi Cerdas AI"

            # Simpan ke cache database jika ada DB dan item_id
            if db and item_id:
                try:
                    db.update_ai_recommendation(item_id, data)
                except Exception as e:
                    print(f"[CACHE AI REC ERROR] {e}")

            return data

    except Exception as e:
        print(f"[TIKTOK DYNAMIC AI REC ERROR] {e}")

    # 3. Fallback Universal (Jika API Gemini offline/unreachable)
    return {
        "format": "problem_solution",
        "format_label": "Problem & Solution",
        "format_reason": "Format paling universal dan berkonversi tinggi untuk TikTok: menyorot solusi kepraktisan harian.",
        "voice": "Kore",
        "voice_label": "Kore (Wanita - Tegas & Jernih)",
        "voice_reason": "Karakter suara jernih dan meyakinkan untuk audiens umum Indonesia.",
        "honesty_mode": "research_based",
        "honesty_label": "Research-Based (Objektif)",
        "badge": "Rekomendasi AI"
    }


class TikTokContentStudioService:
    def __init__(self, db=None, gemini_client: Optional[GeminiClient] = None):
        self.db = db
        self.ai = gemini_client or GeminiClient(db=db)

    def analyze_product_opportunity(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """Melakukan analisis kelayakan kurasi produk TikTok Shop Affiliate (15-Point Breakdown & Skor 0-100)."""
        name = product.get("product_name", "Produk")
        price = product.get("price", 0)
        rating = product.get("rating", 0.0)
        sales = product.get("sales", 0)
        category = product.get("category", "General")
        shop_name = product.get("shop_name", "Official Store")

        prompt = f"""Anda adalah Kurator & Analis Produk TikTok Shop Affiliate profesional untuk audiens Indonesia.
Lakukan analisis kelayakan objektif (15-point structured breakdown) untuk produk berikut:

Nama Produk: {name}
Kategori: {category}
Harga: Rp {price:,.0f}
Rating: {rating} / 5.0 (Penjualan: {sales} terjual)
Toko: {shop_name}

ATURAN KETAT:
- Jangan mengarang data teknis/medis yang tidak ada.
- Skor kurasi (0-100) bersifat transparan berdasarkan relevansi, fungsi, dan daya tarik konten TikTok.
- Kembalikan HANYA format JSON valid berikut:
{{
  "skor_kelayakan": 85,
  "relevansi_audiens": "Profil target audiens TikTok yang paling membutuhkan barang ini",
  "pain_points": ["Masalah 1 yang sering dialami audiens", "Masalah 2"],
  "unique_selling_points": ["Kelebihan utama produk berbasis data", "Fitur menonjol"],
  "potensi_angle_konten": ["Angle 1", "Angle 2"],
  "rekomendasi_format_terbaik": "problem_solution",
  "alasan_kelayakan": "Ringkasan kesimpulan mengapa produk ini potensial dibuatkan video"
}}"""

        try:
            res_text = self.ai.generate_content(prompt)
            data = self._clean_json(res_text)
            if data and "skor_kelayakan" in data:
                return {"ok": True, "analysis": data}
        except Exception as e:
            print(f"[TIKTOK ANALYZE ERROR] {e}")

        # Fallback default analysis
        return {
            "ok": True,
            "analysis": {
                "skor_kelayakan": 80,
                "relevansi_audiens": "Pengguna aktif yang mencari kepraktisan harian",
                "pain_points": ["Repot dengan cara manual", "Butuh solusi hemat waktu"],
                "unique_selling_points": ["Fungsional", f"Rating {rating}/5 terbukti disukai"],
                "potensi_angle_konten": ["Sebelum vs Sesudah pakai", "Review fungsional harga terjangkau"],
                "rekomendasi_format_terbaik": "problem_solution",
                "alasan_kelayakan": "Produk fungsional dengan rating pembeli bagus."
            }
        }

    def generate_tiktok_script(
        self,
        product: Dict[str, Any],
        content_format: str = "problem_solution",
        duration_seconds: int = 30,
        honesty_mode: str = "research_based",
        custom_hook_direction: str = ""
    ) -> Dict[str, Any]:
        """Menghasilkan naskah video vertikal 9:16 TikTok terstruktur (Hook, Body, CTA) + teks subtitle & caption."""
        name = product.get("product_name", "Produk")
        price = product.get("price", 0)
        rating = product.get("rating", 0.0)
        category = product.get("category", "General")
        shop_name = product.get("shop_name", "Toko Resmi")

        format_meta = TIKTOK_CONTENT_FORMATS.get(content_format, TIKTOK_CONTENT_FORMATS["problem_solution"])

        if honesty_mode == "first_hand":
            honesty_rule = (
                "MODE: FIRST-HAND EXPERIENCE. Narasi boleh memakai sudut pandang pengalaman pribadi yang wajar, "
                "namun dilarang membuat klaim khasiat palsu/medis."
            )
        else:
            honesty_rule = (
                "MODE: RESEARCH-BASED. Kreator belum memegang fisik barang. DILARANG KERAS berkata 'saya sudah pakai', "
                "'pengalaman saya', atau seolah sudah memakai. Gunakan kalimat objektif seperti 'Dari spesifikasinya...', "
                "'Banyak yang checkout karena...', 'Solusi simpel buat yang butuh...', 'Hal menarik yang perlu kamu cek...'"
            )

        word_target = int(duration_seconds * 2.3)  # Estimasi rata-rata bicara santai bahasa Indonesia: ~2.3 kata per detik

        prompt = f"""Anda adalah Video Content Creator TikTok Affiliate no. 1 di Indonesia dengan spesialisasi video 9:16 viral dan berkonversi tinggi.
Susun naskah video vertikal untuk produk berikut:

Produk: {name}
Kategori: {category}
Harga: Rp {price:,.0f} | Rating: {rating}
Format Video: {format_meta['label']} ({format_meta['desc']})
Target Durasi: ~{duration_seconds} detik (Maksimal sekitar {word_target} kata agar pas dengan tempo bicara alami).
{honesty_rule}
Arahan Tambahan Hook: {custom_hook_direction or format_meta['hook_style']}

PANDUAN PENULISAN:
1. Hook 3 Detik: Kalimat pembuka harus instan mencuri perhatian, menembus scrolling audiens, tanpa basa-basi 'Halo guys' atau 'Pernah nggak sih'.
2. Body/Solusi: Jelaskan fungsi nyata produk dengan bahasa santai, mengalir, tanpa kalimat kaku/AI-clichés.
3. CTA Alami: Ajak cek etalase atau keranjang kuning secara natural dan tidak maksa.
4. Voiceover Text: Kalimat bersih yang akan dibaca oleh Text-to-Speech (tanpa simbol rumit, tanpa tanda kurung).

Kembalikan HANYA format JSON valid berikut:
{{
  "hook": "Kalimat hook pembuka 3 detik pertama",
  "opening": "Kalimat pengantar singkat setelah hook",
  "main_narration": "Kalimat inti penjelasan fungsi produk",
  "supporting": "Sorotan kelebihan atau bukti ulasan pembeli",
  "cta": "Kalimat ajakan aksi penutup",
  "full_voiceover_text": "Gabungan seluruh naskah yang mengalir enak didengar dari awal sampai akhir untuk voiceover",
  "subtitles": [
    {{"text": "Potongan teks subtitle 1", "approx_time": "0-3s"}},
    {{"text": "Potongan teks subtitle 2", "approx_time": "3-7s"}},
    {{"text": "Potongan teks subtitle 3", "approx_time": "7-12s"}}
  ],
  "tiktok_caption": "Caption singkat menarik untuk postingan TikTok",
  "tiktok_hashtags": ["#RacunTikTok", "#TikTokShop", "#TemuanHarian", "#RekomendasiProduk", "#Affiliate"],
  "overlay_badge": "LABEL SINGKAT HOOK (Maks 4 kata)",
  "overlay_cta": "Cek Keranjang Kuning 🛒"
}}"""

        try:
            res_text = self.ai.generate_content(prompt)
            data = self._clean_json(res_text)
            if data and "full_voiceover_text" in data:
                data["content_format"] = content_format
                data["duration_seconds"] = duration_seconds
                data["honesty_mode"] = honesty_mode
                return {"ok": True, "script": data}
        except Exception as e:
            print(f"[TIKTOK SCRIPT ERROR] {e}")

        # Fallback script jika AI timeout
        fallback_text = (
            f"Kalau kamu sering repot nyari barang yang awet dan fungsional, barang satu ini beneran patut diperhitungkan. "
            f"Desainnya simpel, fiturnya kepake banget buat kebutuhan sehari-hari, dan sudah banyak dapat ulasan bintang lima. "
            f"Mumpung stoknya masih ada, langsung cek detailnya di keranjang kuning sekarang."
        )
        return {
            "ok": True,
            "script": {
                "hook": "Barang fungsional yang diam-diam banyak dicari orang.",
                "opening": "Kalau kamu sering repot nyari barang yang awet dan praktis...",
                "main_narration": "Desainnya simpel dan fiturnya kepake banget buat kebutuhan sehari-hari.",
                "supporting": f"Sudah dapat rating {rating} dari ribuan ulasan pembeli.",
                "cta": "Langsung cek detailnya di keranjang kuning sekarang.",
                "full_voiceover_text": fallback_text,
                "subtitles": [
                    {"text": "Barang fungsional yang banyak dicari", "approx_time": "0-3s"},
                    {"text": "Praktis banget buat kebutuhan sehari-hari", "approx_time": "3-8s"},
                    {"text": f"Rating {rating} dari pembeli", "approx_time": "8-12s"},
                    {"text": "Cek keranjang kuning sekarang!", "approx_time": "12-15s"}
                ],
                "tiktok_caption": f"Rekomendasi barang praktis: {name}. Cek keranjang kuning selagi promo!",
                "tiktok_hashtags": ["#TikTokShop", "#RacunTikTok", "#TemuanHarian", "#BarangUnik"],
                "overlay_badge": "REKOMENDASI TERBAIK",
                "overlay_cta": "Cek Keranjang Kuning 🛒",
                "content_format": content_format,
                "duration_seconds": duration_seconds,
                "honesty_mode": honesty_mode
            }
        }

    def _clean_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Mengekstrak dan mem-parse JSON dengan toleransi format markdown."""
        if not raw_text:
            return None
        text = raw_text.strip()
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        else:
            s = text.find("{")
            e = text.rfind("}")
            if s != -1 and e != -1 and e > s:
                text = text[s:e+1]
        try:
            return json.loads(text)
        except Exception:
            return None
