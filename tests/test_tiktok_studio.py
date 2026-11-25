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
        # 1. Test cached AI recommendation
        cached_prod = {
            "item_id": "test_1",
            "product_name": "Barang Random Unik 2026",
            "ai_recommendation": '{"format": "viral_showcase", "format_label": "Viral Showcase", "voice": "Aoede", "voice_label": "Aoede (Santai)", "format_reason": "Alasan AI", "voice_reason": "Suara pas", "badge": "Barang Viral"}'
        }
        rec = get_recommended_settings(cached_prod)
        self.assertEqual(rec["format"], "viral_showcase")
        self.assertEqual(rec["voice"], "Aoede")
        self.assertEqual(rec["badge"], "Barang Viral")

        # 2. Test dynamic reasoning with mock Gemini AI
        from unittest.mock import MagicMock
        mock_gemini = MagicMock()
        mock_gemini.generate_content.return_value = """{
            "format": "problem_solution",
            "format_label": "Problem & Solution",
            "format_reason": "Produk ini menyelesaikan masalah spesifik",
            "voice": "Charon",
            "voice_label": "Charon (Informatif)",
            "voice_reason": "Artikulasi tenang",
            "honesty_mode": "research_based",
            "badge": "Solusi Efektif"
        }"""
        random_prod = {
            "item_id": "test_2",
            "product_name": "Produk Niche Apa Saja Yang Tidak Pernah Ada Sebelumnya",
            "category": "Kategori Baru",
            "price": 75000
        }
        dyn_rec = get_recommended_settings(random_prod, gemini_client=mock_gemini)
        self.assertEqual(dyn_rec["format"], "problem_solution")
        self.assertEqual(dyn_rec["voice"], "Charon")
        self.assertEqual(dyn_rec["badge"], "Solusi Efektif")

        # 3. Test fallback when Gemini fails
        mock_fail_gemini = MagicMock()
        mock_fail_gemini.generate_content.side_effect = RuntimeError("API Offline")
        fallback_rec = get_recommended_settings(random_prod, gemini_client=mock_fail_gemini)
        self.assertEqual(fallback_rec["format"], "problem_solution")
        self.assertEqual(fallback_rec["voice"], "Kore")

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
