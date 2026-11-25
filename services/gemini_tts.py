"""Layanan Text-to-Speech (TTS) Bahasa Indonesia menggunakan Google Gemini Developer API.
Menggunakan model gemini-2.5-flash-preview-tts dengan suara prebuilt resmi.
Menerima raw PCM linear 16-bit 24kHz dan mengonversi otomatis ke MP3/WAV via FFmpeg.
"""
import os
import json
import base64
import tempfile
import subprocess
from typing import Dict, Any, Optional

VOICE_PROFILES = {
    "Kore": {
        "name": "Kore",
        "gender": "Female",
        "tone": "Firm & Jernih",
        "desc": "Cocok untuk review produk & edukasi fungsional",
        "style_prompt": "Ucapkan dengan gaya ramah, jelas, percaya diri, dan natural dalam Bahasa Indonesia:"
    },
    "Puck": {
        "name": "Puck",
        "gender": "Male",
        "tone": "Upbeat & Ceria",
        "desc": "Cocok untuk konten TikTok viral, flash sale & promo energik",
        "style_prompt": "Ucapkan dengan gaya ceria, antusias, berenergi, dan ekspresif dalam Bahasa Indonesia:"
    },
    "Aoede": {
        "name": "Aoede",
        "gender": "Female",
        "tone": "Breezy & Santai",
        "desc": "Cocok untuk storytelling, curhat ramah & rekomendasi kasual",
        "style_prompt": "Ucapkan dengan nada santai, akrab, hangat, dan mengalir seperti teman ngobrol dalam Bahasa Indonesia:"
    },
    "Charon": {
        "name": "Charon",
        "gender": "Male",
        "tone": "Informatif & Tenang",
        "desc": "Cocok untuk tutorial, unboxing teknis & tips mendalam",
        "style_prompt": "Ucapkan dengan nada tenang, berwibawa, terpercaya, dan informatif dalam Bahasa Indonesia:"
    },
    "Fenrir": {
        "name": "Fenrir",
        "gender": "Male",
        "tone": "Dinamis & Antusias",
        "desc": "Cocok untuk hook cepat, highlight fitur unik & call to action",
        "style_prompt": "Ucapkan dengan intonasi dinamis, cepat, menarik rasa penasaran dalam Bahasa Indonesia:"
    }
}


class GeminiTTSService:
    def __init__(self, api_key: Optional[str] = None, db = None):
        self.db = db
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key and db:
            try:
                self.api_key = db.get_setting("gemini_api_key") or ""
            except Exception:
                pass
        self.model = "gemini-2.5-flash-preview-tts"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def _get_api_key(self) -> str:
        if not self.api_key or not os.getenv('GEMINI_API_KEY'):
            for p in ['.env', os.path.join(os.path.dirname(__file__), '..', '.env')]:
                if os.path.exists(p):
                    try:
                        with open(p, 'r') as ef:
                            for l in ef:
                                if l.strip().startswith('GEMINI_API_KEY='):
                                    v = l.strip().split('=', 1)[1].strip("' ")
                                    if v:
                                        self.api_key = v
                                        os.environ['GEMINI_API_KEY'] = v
                                        return v
                    except Exception:
                        pass
        if self.api_key:
            return self.api_key
        if self.db:
            try:
                val = self.db.get_setting("gemini_api_key")
                if val:
                    self.api_key = val
                    return val
            except Exception:
                pass
        return os.getenv("GEMINI_API_KEY", "")

    def get_audio_duration(self, audio_file_path: str) -> float:
        """Mengambil durasi tepat file audio dalam detik via ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_file_path
            ]
            dur_str = subprocess.check_output(cmd, stderr=subprocess.PIPE).decode().strip()
            return float(dur_str)
        except Exception as e:
            print(f"[FFPROBE ERROR] Gagal mendeteksi durasi audio: {e}")
            return 0.0

    def synthesize(
        self,
        text: str,
        voice_name: str = "Kore",
        output_path: Optional[str] = None,
        speed_factor: float = 1.0
    ) -> Dict[str, Any]:
        """Menghasilkan audio MP3 narasi bahasa Indonesia dari teks.
        
        Args:
            text: Naskah yang akan diucapkan.
            voice_name: Nama suara (Kore, Puck, Aoede, Charon, Fenrir).
            output_path: Path file tujuan (.mp3). Jika None, dibuatkan file sementara.
            speed_factor: Kecepatan audio (misal 1.05x atau 1.1x via atempo ffmpeg filter).
        """
        import requests

        key = self._get_api_key()
        if not key:
            return {
                "ok": False,
                "error": "GEMINI_API_KEY belum dikonfigurasi. Masukkan di menu Pengaturan API."
            }

        voice_meta = VOICE_PROFILES.get(voice_name, VOICE_PROFILES["Kore"])
        style_prompt = voice_meta["style_prompt"]
        full_prompt = f"{style_prompt}\n{text.strip()}"

        url = f"{self.base_url}/{self.model}:generateContent?key={key}"
        payload = {
            "contents": [{
                "parts": [{"text": full_prompt}]
            }],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                }
            }
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=45)
            if resp.status_code != 200:
                err_body = resp.text[:300]
                return {
                    "ok": False,
                    "error": f"Gemini TTS API error (HTTP {resp.status_code}): {err_body}"
                }

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return {"ok": False, "error": "Respons Gemini tidak memiliki data suara."}

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts or "inlineData" not in parts[0]:
                return {"ok": False, "error": "Format data audio Gemini tidak sesuai."}

            inline_data = parts[0]["inlineData"]
            b64_audio = inline_data.get("data", "")
            pcm_bytes = base64.b64decode(b64_audio)

            # Tentukan output path
            if not output_path:
                temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                output_path = temp_file.name
                temp_file.close()

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

            # Simpan PCM mentah ke temp
            with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as pcm_tmp:
                pcm_tmp.write(pcm_bytes)
                pcm_tmp_path = pcm_tmp.name

            try:
                # Filter audio tempo jika speed_factor != 1.0
                tempo_filter = []
                if 0.5 <= speed_factor <= 2.0 and speed_factor != 1.0:
                    tempo_filter = ["-filter:a", f"atempo={speed_factor}"]

                cmd = [
                    "ffmpeg", "-y",
                    "-f", "s16le", "-ar", "24000", "-ac", "1",
                    "-i", pcm_tmp_path,
                    *tempo_filter,
                    "-ar", "44100", "-ac", "2", "-b:a", "192k",
                    output_path
                ]
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if proc.returncode != 0:
                    return {
                        "ok": False,
                        "error": f"FFmpeg gagal mengonversi audio: {proc.stderr.decode()[:200]}"
                    }

                duration = self.get_audio_duration(output_path)
                return {
                    "ok": True,
                    "output_path": output_path,
                    "duration": duration,
                    "voice_name": voice_name,
                    "voice_tone": voice_meta["tone"]
                }
            finally:
                if os.path.exists(pcm_tmp_path):
                    try:
                        os.unlink(pcm_tmp_path)
                    except Exception:
                        pass

        except Exception as e:
            return {"ok": False, "error": f"Gagal mengeksekusi Gemini TTS: {str(e)}"}
