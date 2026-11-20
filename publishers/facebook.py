"""Publisher Facebook Page via Graph API (Meta v27.0).
Menerapkan ISocialPublisher (Single Responsibility & Liskov Substitution).
"""
import os
from typing import Optional
import requests
from core.interfaces import ISocialPublisher


class FacebookError(RuntimeError):
    pass


class FacebookPagePublisher(ISocialPublisher):
    """Publisher resmi untuk Halaman Facebook (Fanspage)."""

    def __init__(
        self,
        page_id: Optional[str] = None,
        access_token: Optional[str] = None,
        version: Optional[str] = None,
        session: Optional[requests.Session] = None,
        db=None,
    ):
        db_page_id = db.get_setting("fb_page_id") if db else None
        db_token = db.get_setting("fb_page_access_token") if db else None

        self.page_id = str(page_id or db_page_id or os.getenv("FB_PAGE_ID", "")).strip()
        self.access_token = str(access_token or db_token or os.getenv("FB_PAGE_ACCESS_TOKEN", "")).strip()
        version = version or os.getenv("FB_GRAPH_VERSION", "v27.0")
        self.base_url = f"https://graph.facebook.com/{version}"
        self.session = session or requests.Session()

        # Header browser standar agar unduhan CDN gambar tidak terkena 403 Forbidden
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        })

        if not self.page_id or not self.access_token:
            raise ValueError(
                "FB_PAGE_ID dan FB_PAGE_ACCESS_TOKEN belum dikonfigurasi. "
                "Silakan atur di Tab Pengaturan Dashboard (/admin) atau file .env"
            )

    @property
    def platform_name(self) -> str:
        return "Facebook Page"

    def _post(self, path: str, data: dict, files: Optional[dict] = None) -> dict:
        payload = dict(data, access_token=self.access_token)
        resp = self.session.post(f"{self.base_url}/{path}", data=payload, files=files, timeout=60)
        try:
            body = resp.json()
        except ValueError:
            raise FacebookError(f"Respons bukan JSON (HTTP {resp.status_code})")
        if "error" in body:
            err = body["error"]
            raise FacebookError(err.get("message", str(err)) if isinstance(err, dict) else str(err))
        return body

    def publish_photo(self, image_url: str, caption: str) -> str:
        """Unduh gambar lalu unggah sebagai file (lebih andal daripada meminta FB menarik URL)."""
        img = self.session.get(image_url, timeout=30)
        img.raise_for_status()
        content_type = img.headers.get("Content-Type", "image/jpeg")
        files = {"source": ("produk.jpg", img.content, content_type)}
        body = self._post(f"{self.page_id}/photos", {"caption": caption}, files=files)
        post_id = body.get("post_id") or body.get("id")
        if not post_id:
            raise FacebookError(f"Respons tanpa id: {body}")
        return str(post_id)

    def publish_video(self, video_url: str, caption: str) -> str:
        """Publikasikan video resmi produk via Graph API v27.0.
        Mencoba unduh video dan unggah langsung sebagai binary source agar tidak diblokir CDN Shopee,
        dengan fallback ke file_url.
        """
        try:
            vid_resp = self.session.get(video_url, timeout=60, stream=True)
            if vid_resp.status_code == 200:
                files = {"source": ("video.mp4", vid_resp.content, "video/mp4")}
                body = self._post(f"{self.page_id}/videos", {"description": caption}, files=files)
                post_id = body.get("id")
                if post_id:
                    return str(post_id)
        except Exception:
            # Fallback ke pengiriman file_url langsung ke Meta
            pass

        body = self._post(f"{self.page_id}/videos", {"file_url": video_url, "description": caption})
        post_id = body.get("id")
        if not post_id:
            raise FacebookError(f"Respons video tanpa id: {body}")
        return str(post_id)

    def add_comment(self, post_id: str, comment_text: str) -> str:
        """Komentar pertama berisi link afiliasi. Membutuhkan izin pages_manage_engagement."""
        body = self._post(f"{post_id}/comments", {"message": comment_text})
        return str(body.get("id", ""))
