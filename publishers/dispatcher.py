"""Multi-Channel Publisher Dispatcher (Open/Closed Principle & Dependency Injection).
Menerima daftar ISocialPublisher via constructor injection dan mengeksekusi publikasi multi-channel.
Mendukung penerbitan foto cover resmi maupun video asli (Real Seller Media).
"""
from typing import List, Dict, Any, Optional
from core.interfaces import ISocialPublisher


class PublishResult:
    def __init__(self):
        self.successful_channels: List[str] = []
        self.failed_channels: Dict[str, str] = {}
        self.post_ids: Dict[str, str] = {}

    @property
    def is_success(self) -> bool:
        return len(self.successful_channels) > 0

    def summary(self) -> str:
        msg = f"Berhasil diposting ke [{', '.join(self.successful_channels)}]." if self.successful_channels else "Tidak ada channel yang berhasil diposting."
        if self.failed_channels:
            fails = [f"{ch} ({err})" for ch, err in self.failed_channels.items()]
            msg += f" (Gagal: {', '.join(fails)})"
        return msg


class PublisherDispatcher:
    """Orkestrator penerbitan multi-channel menggunakan Dependency Injection."""

    def __init__(self, publishers: List[ISocialPublisher]):
        # Dependency Injection: menerima daftar publisher yang sudah diinisialisasi
        self.publishers = publishers

    def dispatch(
        self,
        image_url: str,
        caption: str,
        comment_text: Optional[str] = None,
        video_url: Optional[str] = None,
        media_type: str = "IMAGE"
    ) -> PublishResult:
        """Memublikasikan media (foto/video asli) dan komentar pertama ke seluruh channel yang aktif."""
        result = PublishResult()

        for publisher in self.publishers:
            name = publisher.platform_name
            try:
                post_id = None
                # 1. Coba publikasikan video jika ada dan publisher mendukung
                if media_type == "VIDEO" and video_url and hasattr(publisher, "publish_video"):
                    try:
                        post_id = publisher.publish_video(video_url=video_url, caption=caption)
                    except Exception as vid_err:
                        # Fallback ke foto jika video gagal
                        if image_url:
                            post_id = publisher.publish_photo(image_url=image_url, caption=caption)
                        else:
                            raise vid_err
                else:
                    # Default: Foto cover resmi
                    post_id = publisher.publish_photo(image_url=image_url, caption=caption)

                result.post_ids[name] = post_id
                result.successful_channels.append(name)

                # 2. Posting komentar link pertama (jika ada)
                if comment_text:
                    try:
                        publisher.add_comment(post_id=post_id, comment_text=comment_text)
                    except Exception as comment_err:
                        # Gagal komentar tidak menggagalkan postingan utama
                        pass

            except Exception as exc:
                result.failed_channels[name] = str(exc)

        return result
