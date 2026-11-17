"""Publisher resmi Threads menggunakan Threads API (Meta v1.0).
Menerapkan ISocialPublisher (Single Responsibility & Liskov Substitution).
"""
import time
import requests
from typing import Dict, Any, Optional
from core.interfaces import ISocialPublisher

THREADS_API_BASE = "https://graph.threads.net/v1.0"


class ThreadsError(Exception):
    pass


class ThreadsPublisher(ISocialPublisher):
    """Publisher resmi untuk Threads."""

    def __init__(self, user_id: str, access_token: str):
        self.user_id = user_id.strip()
        self.access_token = access_token.strip()

    @property
    def platform_name(self) -> str:
        return "Threads"

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{THREADS_API_BASE}/{path}"
        payload["access_token"] = self.access_token
        try:
            resp = requests.post(url, data=payload, timeout=30)
            data = resp.json()
        except requests.RequestException as e:
            raise ThreadsError(f"Network error ke Threads API: {e}") from e

        if resp.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            msg = err.get("message", resp.text)
            raise ThreadsError(f"Threads API Error ({resp.status_code}): {msg}")

        return data

    def publish_photo(self, image_url: str, caption: str) -> str:
        """Membuat wadah media gambar Threads dan mempublikasikannya."""
        # Langkah 1: Buat media container
        container_data = self._post(
            f"{self.user_id}/threads",
            {
                "media_type": "IMAGE",
                "image_url": image_url,
                "text": caption,
            }
        )
        creation_id = container_data.get("id")
        if not creation_id:
            raise ThreadsError("Gagal mendapatkan creation_id dari Threads API")

        # Beri jeda singkat agar processing selesai di server Meta
        time.sleep(2)

        # Langkah 2: Publikasikan container
        publish_data = self._post(
            f"{self.user_id}/threads_publish",
            {"creation_id": creation_id}
        )
        thread_id = publish_data.get("id")
        if not thread_id:
            raise ThreadsError("Gagal mempublikasikan thread di Threads API")

        return str(thread_id)

    def add_comment(self, post_id: str, comment_text: str) -> str:
        """Menambahkan balasan/komentar pertama berisi link afiliasi di thread."""
        container_data = self._post(
            f"{self.user_id}/threads",
            {
                "media_type": "TEXT",
                "text": comment_text,
                "reply_to_id": post_id,
            }
        )
        reply_creation_id = container_data.get("id")
        if not reply_creation_id:
            raise ThreadsError("Gagal membuat reply container di Threads")

        time.sleep(1)

        publish_data = self._post(
            f"{self.user_id}/threads_publish",
            {"creation_id": reply_creation_id}
        )
        return str(publish_data.get("id", ""))
