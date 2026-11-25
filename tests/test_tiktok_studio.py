"""Unit tests untuk TikTok Studio: Gemini TTS, Script Generator, Video Producer, dan Smart Recommendation Engine."""
import os
import unittest
from services.gemini_tts import VOICE_PROFILES, GeminiTTSService
from services.tiktok_script import TIKTOK_CONTENT_FORMATS, TikTokContentStudioService, get_recommended_settings
from services.video_producer import TikTokVideoProducer


class TestTikTokStudio(unittest.TestCase):
    def test_voice_profiles(self):
        self.assertIn("Kore", VOICE_PROFILES)
        self.assertIn("Puck", VOICE_PROFILES)
        self.assertIn("Aoede", VOICE_PROFILES)
        self.assertIn("Charon", VOICE_PROFILES)
        self.assertIn("Fenrir", VOICE_PROFILES)
        self.assertEqual(VOICE_PROFILES["Kore"]["gender"], "Female")

    def test_content_formats(self):
        self.assertIn("problem_solution", TIKTOK_CONTENT_FORMATS)
        self.assertIn("product_review", TIKTOK_CONTENT_FORMATS)
        self.assertIn("product_showcase", TIKTOK_CONTENT_FORMATS)
        self.assertIn("top_recommendations", TIKTOK_CONTENT_FORMATS)
        self.assertIn("educational_explainer", TIKTOK_CONTENT_FORMATS)

    def test_get_recommended_settings_mappings(self):
        # 1. Tools / Pertukangan
        bor = {"product_name": "Mata Bor Beton Karbida 10mm", "category": "Pertukangan", "price": 45000}
        rec_bor = get_recommended_settings(bor)
        self.assertEqual(rec_bor["format"], "problem_solution")
        self.assertEqual(rec_bor["voice"], "Kore")

        # 2. Fashion
        kaos = {"product_name": "Kaos Polos Oversize Katun Combed 24s", "category": "Fashion Pria", "price": 65000}
        rec_kaos = get_recommended_settings(kaos)
        self.assertEqual(rec_kaos["format"], "product_showcase")
        self.assertEqual(rec_kaos["voice"], "Aoede")

        # 3. Kuliner / Camilan
        keripik = {"product_name": "Keripik Kaca Pedas Daun Jeruk 250g", "category": "Makanan & Minuman", "price": 25000}
        rec_keripik = get_recommended_settings(keripik)
        self.assertEqual(rec_keripik["format"], "product_showcase")
        self.assertEqual(rec_keripik["voice"], "Puck")

        # 4. Gadget
        tws = {"product_name": "TWS Bluetooth 5.3 Bass Earphone", "category": "Aksesoris Handphone", "price": 99000}
        rec_tws = get_recommended_settings(tws)
        self.assertEqual(rec_tws["format"], "product_review")
        self.assertEqual(rec_tws["voice"], "Charon")

        # 5. Skincare
        serum = {"product_name": "Serum Brightening Niacinamide 10%", "category": "Kecantikan & Perawatan", "price": 85000}
        rec_serum = get_recommended_settings(serum)
        self.assertEqual(rec_serum["format"], "educational_explainer")
        self.assertEqual(rec_serum["voice"], "Aoede")

        # 6. Budget Deal (< 40rb)
        murah = {"product_name": "Sticker Lucu Pack Aesthetic", "category": "Lainnya", "price": 15000}
        rec_murah = get_recommended_settings(murah)
        self.assertEqual(rec_murah["format"], "top_recommendations")
        self.assertEqual(rec_murah["voice"], "Puck")

    def test_video_producer_canvas_render(self):
        producer = TikTokVideoProducer()
        dummy_prod = {
            "product_name": "Test Product",
            "category": "Elektronik",
            "price": 50000,
            "rating": 4.9,
            "sales": 100
        }
        dummy_script = {
            "hook": "Barang unik yang wajib kamu tahu",
            "overlay_badge": "REKOMENDASI HARIAN",
            "overlay_cta": "Cek Keranjang Kuning"
        }
        canvas = producer.render_canvas_frame(dummy_prod, dummy_script, active_subtitle="Barang unik ini!")
        self.assertEqual(canvas.size, (1080, 1920))
        self.assertEqual(canvas.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
