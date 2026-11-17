"""Publisher resmi Instagram menggunakan Instagram Graph API (Meta v25.0).
Menerapkan ISocialPublisher (Single Responsibility & Liskov Substitution).
"""
import time
import requests
from typing import Optional
from core.interfaces import ISocialPublisher

GRAPH_VERSION = "v25.0"
FB_GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


class InstagramError(Exception):
    pass


class InstagramPublisher(ISocialPublisher):
    """Publisher resmi untuk Instagram Business / Creator Feed."""

    def __init__(self, ig_user_id: str, access_token: str):
        self.ig_user_id = ig_user_id.strip()
        self.access_token = access_token.strip()

    @property
    def platform_name(self) -> str:
        return "Instagram"

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{FB_GRAPH_BASE}/{path}"
        payload["access_token"] = self.access_token
        try:
            resp = requests.post(url, data=payload, timeout=30)
            data = resp.json()
        except requests.RequestException as e:
            raise InstagramError(f"Network error ke Instagram API: {e}") from e

        if resp.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            msg = err.get("message", resp.text)
            raise InstagramError(f"Instagram API Error ({resp.status_code}): {msg}")

        return data

    def publish_photo(self, image_url: str, caption: str) -> str:
        """Membuat kontainer media Instagram dan mempublikasikannya."""
        # 1. Buat kontainer foto
        container_data = self._post(
            f"{self.ig_user_id}/media",
            {
                "image_url": image_url,
                "caption": caption,
            }
        )
        creation_id = container_data.get("id")
        if not creation_id:
            raise InstagramError("Gagal membuat kontainer media Instagram")

        # Jeda waktu agar pemrosesan gambar selesai di CDN Instagram
        time.sleep(3)

        # 2. Publikasikan media
        publish_data = self._post(
            f"{self.ig_user_id}/media_publish",
            {"creation_id": creation_id}
        )
        media_id = publish_data.get("id")
        if not media_id:
            raise InstagramError("Gagal mempublikasikan postingan Instagram")

        return str(media_id)

    def add_comment(self, post_id: str, comment_text: str) -> str:
        """Menambahkan komentar pertama berisi link afiliasi di Instagram."""
        data = self._post(
            f"{post_id}/comments",
            {"message": comment_text}
        )
        return str(data.get("id", ""))
