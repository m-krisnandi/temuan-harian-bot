"""Unit tests untuk TikTok Studio: Gemini TTS, Script Generator, dan Video Producer."""
import os
import unittest
from services.gemini_tts import VOICE_PROFILES, GeminiTTSService
from services.tiktok_script import TIKTOK_CONTENT_FORMATS, TikTokContentStudioService
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
