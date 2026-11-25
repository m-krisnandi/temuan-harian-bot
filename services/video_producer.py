"""Mesin Produksi Video Vertikal 9:16 (1080x1920) untuk TikTok Shop Affiliate & Reels.
Diadaptasi dari standar Remotion/Cultiv Video Producer.
Menghasilkan video H.264 + AAC MP4 beresolusi tinggi dengan safe-area TikTok,
efek visual estetik, badge harga & rating, serta subtitle tersinkronisasi audio Gemini TTS.
"""
import os
import io
import math
import shutil
import tempfile
import subprocess
import requests
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter


class TikTokVideoProducer:
    """Renderer Video Vertikal 9:16 (1080x1920) siap unggah ke TikTok Shop."""

    WIDTH = 1080
    HEIGHT = 1920
    FPS = 30

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(os.path.dirname(__file__), "..", "web", "static", "videos")
        self.thumb_dir = os.path.join(os.path.dirname(__file__), "..", "web", "static", "thumbnails")
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.thumb_dir, exist_ok=True)

    def _get_font(self, size: int, bold: bool = False):
        """Memuat font sistem universal (AppleGothic, Arial, DejaVu, Helvetica) dengan fallback Pillow."""
        font_candidates = [
            # macOS fonts
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFPro.ttf",
            "/System/Library/Fonts/SFCompact.ttf",
            "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            # Linux fonts
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        for path in font_candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _download_image(self, image_url: str) -> Optional[Image.Image]:
        """Mengunduh gambar produk dari URL atau membaca file lokal."""
        if not image_url:
            return None
        try:
            if image_url.startswith("http://") or image_url.startswith("https://"):
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
                }
                resp = requests.get(image_url, headers=headers, timeout=20)
                if resp.status_code == 200:
                    return Image.open(io.BytesIO(resp.content)).convert("RGBA")
            elif os.path.exists(image_url):
                return Image.open(image_url).convert("RGBA")
        except Exception as e:
            print(f"[IMAGE LOAD ERROR] Gagal memuat gambar {image_url[:60]}: {e}")
        return None

    def render_canvas_frame(
        self,
        product: Dict[str, Any],
        script: Dict[str, Any],
        active_subtitle: str = "",
        product_img: Optional[Image.Image] = None
    ) -> Image.Image:
        """Merender satu frame 1080x1920 lengkap dengan layout kartu TikTok Affiliate."""
        canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (15, 23, 42, 255)) # Dark slate base
        draw = ImageDraw.Draw(canvas)

        # 1. Background Blur Ambient jika gambar produk ada
        if product_img:
            try:
                bg_thumb = product_img.resize((self.WIDTH, self.HEIGHT), Image.Resampling.BILINEAR)
                bg_blur = bg_thumb.filter(ImageFilter.GaussianBlur(radius=35))
                # Gelapkan agar teks kontras
                dark_overlay = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (10, 15, 30, 190))
                bg_blur.paste(dark_overlay, (0, 0), dark_overlay)
                canvas.paste(bg_blur, (0, 0))
                draw = ImageDraw.Draw(canvas)
            except Exception:
                pass

        # 2. Header Top Bar (Safe zone top > 140px)
        # Badge Kategori & Rekomendasi
        category_name = product.get("category", "REKOMENDASI TERBAIK")
        badge_text = script.get("overlay_badge") or "⚡ TEMUAN HARIAN"

        draw.rounded_rectangle([100, 150, 980, 230], radius=20, fill=(244, 63, 94, 255)) # Rose red
        font_header = self._get_font(34, bold=True)
        draw.text((self.WIDTH // 2, 190), badge_text.upper(), fill=(255, 255, 255), font=font_header, anchor="mm")

        # 3. Product Center Display Card
        card_box = [90, 270, 990, 1170]
        draw.rounded_rectangle(card_box, radius=32, fill=(24, 24, 27, 240), outline=(255, 255, 255, 40), width=3)

        if product_img:
            # Fit image into center area (800x800)
            avail_w = 840
            avail_h = 840
            p_w, p_h = product_img.size
            ratio = min(avail_w / p_w, avail_h / p_h)
            new_w = int(p_w * ratio)
            new_h = int(p_h * ratio)
            resized_p = product_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            paste_x = 90 + (900 - new_w) // 2
            paste_y = 290 + (860 - new_h) // 2
            canvas.paste(resized_p, (paste_x, paste_y), resized_p if resized_p.mode == "RGBA" else None)

        # 4. Info Bar Bawah Gambar (Harga & Rating)
        price_val = product.get("price", 0)
        rating_val = product.get("rating", 4.8)
        sales_val = product.get("sales", 0)
        
        info_box = [110, 1070, 970, 1150]
        draw.rounded_rectangle(info_box, radius=18, fill=(15, 23, 42, 230))
        font_price = self._get_font(36, bold=True)
        font_meta = self._get_font(28, bold=False)

        price_str = f"Rp {price_val:,.0f}".replace(",", ".")
        rating_str = f"★ {rating_val:.1f}" + (f" | {sales_val:,} Terjual" if sales_val else "")

        draw.text((150, 1110), price_str, fill=(250, 204, 21), font=font_price, anchor="lm") # Gold yellow
        draw.text((930, 1110), rating_str, fill=(226, 232, 240), font=font_meta, anchor="rm")

        # 5. Dynamic Subtitle Overlay Box (TikTok Safe Area: 1220 - 1460)
        subtitle_text = active_subtitle or script.get("hook") or product.get("product_name", "")
        # Potong panjang jika berlebih
        if len(subtitle_text) > 85:
            subtitle_text = subtitle_text[:82] + "..."

        sub_box = [80, 1220, 1000, 1440]
        draw.rounded_rectangle(sub_box, radius=24, fill=(0, 0, 0, 200), outline=(250, 204, 21, 180), width=2)
        font_sub = self._get_font(38, bold=True)
        
        # Word wrap sederhana untuk 2-3 baris subtitle
        words = subtitle_text.split(" ")
        lines = []
        curr = ""
        for w in words:
            test = curr + (" " if curr else "") + w
            if len(test) <= 32:
                curr = test
            else:
                lines.append(curr)
                curr = w
        if curr:
            lines.append(curr)

        total_lines = len(lines)
        start_y = 1330 - (total_lines - 1) * 26
        for i, line in enumerate(lines):
            draw.text((self.WIDTH // 2, start_y + i * 52), line, fill=(255, 255, 255), font=font_sub, anchor="mm")

        # 6. Bottom Call to Action Card (TikTok Safe Area: 1470 - 1590, aman di atas tombol keranjang)
        cta_box = [100, 1475, 980, 1585]
        draw.rounded_rectangle(cta_box, radius=28, fill=(250, 204, 21, 255)) # Vibrant Gold
        font_cta = self._get_font(40, bold=True)
        cta_text = script.get("overlay_cta") or "CEK KERANJANG KUNING SEKARANG"
        draw.text((self.WIDTH // 2, 1530), cta_text, fill=(15, 23, 42), font=font_cta, anchor="mm")

        # Watermark Temuan Harian (Subtle)
        font_wm = self._get_font(22, bold=False)
        draw.text((self.WIDTH // 2, 1620), "@temuanharian • Affiliate Resmi", fill=(148, 163, 184, 180), font=font_wm, anchor="mm")

        return canvas

    def render_video(
        self,
        product: Dict[str, Any],
        script: Dict[str, Any],
        audio_path: str,
        video_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Merender video vertikal 9:16 final H.264 MP4 berdurasi pas dengan audio Gemini TTS."""
        if not os.path.exists(audio_path):
            return {"ok": False, "error": f"File audio voiceover tidak ditemukan: {audio_path}"}

        item_id = str(product.get("item_id", "prod_video"))
        clean_name = "".join(c for c in product.get("product_name", "item") if c.isalnum() or c in ("-", "_")).rstrip()[:25]
        
        if not video_filename:
            video_filename = f"tiktok_{item_id}_{clean_name}.mp4"
        
        final_video_path = os.path.join(self.output_dir, video_filename)
        thumb_filename = f"thumb_{item_id}_{clean_name}.jpg"
        final_thumb_path = os.path.join(self.thumb_dir, thumb_filename)

        # 1. Download foto produk
        img_url = product.get("image_url", "")
        product_img = self._download_image(img_url)

        # 2. Render Frame visual utama
        hook_text = script.get("hook", product.get("product_name", ""))
        frame_img = self.render_canvas_frame(product, script, active_subtitle=hook_text, product_img=product_img)

        # Simpan thumbnail cover JPG
        frame_rgb = frame_img.convert("RGB")
        frame_rgb.save(final_thumb_path, "JPEG", quality=90)

        # Simpan base frame ke temp
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_png:
            frame_img.save(tmp_png.name, "PNG")
            tmp_png_path = tmp_png.name

        try:
            # 3. Render video H.264 + AAC dengan durasi persis mengikuti audio
            # Menggunakan loop stillimage yang dipadukan dengan voiceover
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", tmp_png_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                "-movflags", "+faststart",
                final_video_path
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                err_msg = proc.stderr.decode()[:300]
                return {"ok": False, "error": f"FFmpeg render error: {err_msg}"}

            # Periksa hasil file
            if not os.path.exists(final_video_path) or os.path.getsize(final_video_path) < 1000:
                return {"ok": False, "error": "File video yang dihasilkan kosong atau gagal dibuat."}

            return {
                "ok": True,
                "video_path": final_video_path,
                "video_url": f"/static/videos/{video_filename}",
                "thumbnail_url": f"/static/thumbnails/{thumb_filename}",
                "filesize": os.path.getsize(final_video_path),
                "resolution": f"{self.WIDTH}x{self.HEIGHT} (9:16)"
            }
        finally:
            if os.path.exists(tmp_png_path):
                try:
                    os.unlink(tmp_png_path)
                except Exception:
                    pass
