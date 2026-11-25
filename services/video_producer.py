"""Mesin Produksi Video Vertikal 9:16 (1080x1920) Dinamis untuk TikTok Shop Affiliate & Reels.
Diadaptasi dari standar Remotion / Cultiv Video Producer.
Menghasilkan video bergerak nyata (motion video):
1. Latar belakang dinamis bergerak (fluid animated gradient background at 30 fps)
2. Transisi multi-adegan (multi-scene cutscenes) dengan subtitle berganti per kalimat
3. Badge hook, masalah, rating, dan CTA interaktif berganti warna & judul per adegan
4. Efek zoom kamera (close-up framing) pada adegan detail fitur
5. Garis durasi dinamis TikTok (progress bar) yang berjalan mulus di bagian bawah layar
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
    """Renderer Video Vertikal 9:16 (1080x1920) dinamis siap unggah ke TikTok Shop."""

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
            return 15.0

    def render_canvas_frame(
        self,
        product: Dict[str, Any],
        script: Dict[str, Any],
        active_subtitle: str = "",
        product_img: Optional[Image.Image] = None,
        badge_text: str = "",
        badge_bg_color: tuple = (244, 63, 94),
        badge_text_color: tuple = (255, 255, 255),
        zoom_factor: float = 1.0,
        highlight_cta: bool = False,
        is_transparent_bg: bool = False
    ) -> Image.Image:
        """Merender satu frame 1080x1920 lengkap dengan layout kartu TikTok Affiliate interaktif."""
        # Jika transparent_bg aktif, outer border tembus pandang agar moving background terlihat
        base_bg = (0, 0, 0, 0) if is_transparent_bg else (15, 23, 42, 255)
        canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), base_bg)
        draw = ImageDraw.Draw(canvas)

        # 1. Background Blur Ambient jika gambar produk ada (hanya jika non-transparan)
        if product_img and not is_transparent_bg:
            try:
                bg_thumb = product_img.resize((self.WIDTH, self.HEIGHT), Image.Resampling.BILINEAR)
                bg_blur = bg_thumb.filter(ImageFilter.GaussianBlur(radius=35))
                dark_overlay = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (10, 15, 30, 190))
                bg_blur.paste(dark_overlay, (0, 0), dark_overlay)
                canvas.paste(bg_blur, (0, 0))
                draw = ImageDraw.Draw(canvas)
            except Exception:
                pass

        # 2. Header Top Bar (Safe zone top > 140px)
        active_badge = badge_text or script.get("overlay_badge") or "⚡ TEMUAN HARIAN"
        draw.rounded_rectangle([100, 150, 980, 230], radius=20, fill=(*badge_bg_color, 255))
        font_header = self._get_font(34, bold=True)
        draw.text((self.WIDTH // 2, 190), active_badge.upper(), fill=badge_text_color, font=font_header, anchor="mm")

        # 3. Product Center Display Card
        card_box = [90, 270, 990, 1170]
        card_outline = (250, 204, 21, 200) if highlight_cta else (255, 255, 255, 45)
        draw.rounded_rectangle(card_box, radius=32, fill=(24, 24, 27, 245), outline=card_outline, width=3)

        if product_img:
            # Fit image into center area (840x840) with dynamic zoom factor
            avail_w = int(840 * zoom_factor)
            avail_h = int(840 * zoom_factor)
            p_w, p_h = product_img.size
            ratio = min(avail_w / p_w, avail_h / p_h)
            new_w = int(p_w * ratio)
            new_h = int(p_h * ratio)
            resized_p = product_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Crop jika zoom melebihi card area
            if new_w > 860 or new_h > 860:
                left = max(0, (new_w - 860) // 2)
                top = max(0, (new_h - 860) // 2)
                resized_p = resized_p.crop((left, top, left + min(860, new_w), top + min(860, new_h)))
                new_w, new_h = resized_p.size

            paste_x = 90 + (900 - new_w) // 2
            paste_y = 290 + (860 - new_h) // 2
            canvas.paste(resized_p, (paste_x, paste_y), resized_p if resized_p.mode == "RGBA" else None)

        # 4. Info Bar Bawah Gambar (Harga & Rating)
        price_val = product.get("price", 0)
        rating_val = product.get("rating", 4.8)
        sales_val = product.get("sales", 0)

        info_box = [110, 1070, 970, 1150]
        draw.rounded_rectangle(info_box, radius=18, fill=(15, 23, 42, 240), outline=(250, 204, 21, 120), width=2)
        font_price = self._get_font(36, bold=True)
        font_meta = self._get_font(28, bold=False)

        price_str = f"Rp {price_val:,.0f}".replace(",", ".")
        rating_str = f"★ {rating_val:.1f}" + (f" | {sales_val:,} Terjual" if sales_val else "")

        draw.text((150, 1110), price_str, fill=(250, 204, 21), font=font_price, anchor="lm")
        draw.text((930, 1110), rating_str, fill=(226, 232, 240), font=font_meta, anchor="rm")

        # 5. Dynamic Subtitle Overlay Box (TikTok Safe Area: 1220 - 1460)
        subtitle_text = active_subtitle or script.get("hook") or product.get("product_name", "")
        if len(subtitle_text) > 90:
            subtitle_text = subtitle_text[:87] + "..."

        sub_box = [80, 1220, 1000, 1440]
        sub_border = (250, 204, 21, 230) if highlight_cta else (244, 63, 94, 200)
        draw.rounded_rectangle(sub_box, radius=24, fill=(0, 0, 0, 225), outline=sub_border, width=3)
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
        text_color = (255, 255, 255) if not highlight_cta else (255, 240, 180)
        for i, line in enumerate(lines):
            draw.text((self.WIDTH // 2, start_y + i * 52), line, fill=text_color, font=font_sub, anchor="mm")

        # 6. Bottom Call to Action Card (TikTok Safe Area: 1475 - 1585)
        cta_box = [100, 1475, 980, 1585]
        cta_color = (234, 179, 8, 255) if highlight_cta else (250, 204, 21, 240)
        cta_outline = (255, 255, 255, 200) if highlight_cta else None
        draw.rounded_rectangle(cta_box, radius=28, fill=cta_color, outline=cta_outline, width=3 if highlight_cta else 0)
        font_cta = self._get_font(38, bold=True)

        cta_text = "👉 KLIK KERANJANG KUNING SEKARANG" if highlight_cta else (script.get("overlay_cta") or "CEK KERANJANG KUNING SEKARANG")
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
        """Merender video vertikal 9:16 dinamis multi-scene H.264 MP4 berdurasi pas dengan audio Gemini TTS."""
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

        # 2. Deteksi durasi audio tepat
        total_duration = self.get_audio_duration(audio_path)
        if total_duration <= 2.0:
            total_duration = 15.0

        # 3. Susun 4 Scene Dinamis berdasarkan naskah narasi
        hook_text = script.get("hook") or product.get("product_name", "")
        opening_text = script.get("opening") or script.get("main_narration") or "Desain simpel dan praktis banget buat kebutuhan sehari-hari."
        body_text = script.get("main_narration") or script.get("supporting") or f"Sudah terbukti disukai dengan rating {product.get('rating', 4.8)}."
        cta_text = script.get("cta") or "Langsung amankan barang ini di keranjang kuning selagi promo!"

        # Jika ada subtitles list dari AI, gunakan teksnya
        subs_list = script.get("subtitles") or []
        if len(subs_list) >= 4:
            hook_text = subs_list[0].get("text", hook_text)
            opening_text = subs_list[1].get("text", opening_text)
            body_text = subs_list[2].get("text", body_text)
            cta_text = subs_list[3].get("text", cta_text)

        scenes_config = [
            {
                "subtitle": hook_text,
                "badge": script.get("overlay_badge") or "🔥 JANGAN SALAH PILIH!",
                "badge_bg": (244, 63, 94), # Rose red
                "badge_fg": (255, 255, 255),
                "zoom": 1.0,
                "highlight_cta": False
            },
            {
                "subtitle": opening_text,
                "badge": "💡 SOLUSI PRAKTIS TERUJI",
                "badge_bg": (16, 185, 129), # Emerald green
                "badge_fg": (255, 255, 255),
                "zoom": 1.12, # Close-up framing
                "highlight_cta": False
            },
            {
                "subtitle": body_text,
                "badge": f"⭐ RATING {product.get('rating', 4.8):.1f} • TERBUKTI DISUKAI",
                "badge_bg": (245, 158, 11), # Amber orange
                "badge_fg": (255, 255, 255),
                "zoom": 1.05,
                "highlight_cta": False
            },
            {
                "subtitle": cta_text,
                "badge": "🛒 CEK KERANJANG KUNING SEKARANG",
                "badge_bg": (234, 179, 8), # Gold
                "badge_fg": (15, 23, 42),
                "zoom": 1.0,
                "highlight_cta": True
            }
        ]

        # Hitung titik waktu peralihan adegan
        t1 = round(total_duration * 0.25, 2)
        t2 = round(total_duration * 0.55, 2)
        t3 = round(total_duration * 0.80, 2)
        time_points = [0.0, t1, t2, t3, total_duration]

        # 4. Render 4 Frame PNG Overlay (transparan di luar kartu)
        scene_png_paths = []
        try:
            for idx, sc in enumerate(scenes_config):
                frame = self.render_canvas_frame(
                    product=product,
                    script=script,
                    active_subtitle=sc["subtitle"],
                    product_img=product_img,
                    badge_text=sc["badge"],
                    badge_bg_color=sc["badge_bg"],
                    badge_text_color=sc["badge_fg"],
                    zoom_factor=sc["zoom"],
                    highlight_cta=sc["highlight_cta"],
                    is_transparent_bg=True
                )

                # Simpan thumbnail cover dari scene 1
                if idx == 0:
                    thumb_frame = self.render_canvas_frame(
                        product=product,
                        script=script,
                        active_subtitle=sc["subtitle"],
                        product_img=product_img,
                        badge_text=sc["badge"],
                        badge_bg_color=sc["badge_bg"],
                        badge_text_color=sc["badge_fg"],
                        is_transparent_bg=False
                    )
                    thumb_frame.convert("RGB").save(final_thumb_path, "JPEG", quality=90)

                tmp_png = tempfile.NamedTemporaryFile(suffix=f"_sc{idx}.png", delete=False)
                frame.save(tmp_png.name, "PNG")
                tmp_png.close()
                scene_png_paths.append(tmp_png.name)

            # 5. Susun Filter Complex FFmpeg: Latar Gerak + Multi-Scene + Progress Bar
            # Layer 0: Moving background gradients (30 fps)
            # Layer 1-4: Scene overlays with time transitions
            # Final: Progress bar on bottom edge
            fc = (
                f"[0:v][1:v]overlay=0:0:enable='between(t,{time_points[0]},{time_points[1]})'[v1];"
                f"[v1][2:v]overlay=0:0:enable='between(t,{time_points[1]},{time_points[2]})'[v2];"
                f"[v2][3:v]overlay=0:0:enable='between(t,{time_points[2]},{time_points[3]})'[v3];"
                f"[v3][4:v]overlay=0:0:enable='gte(t,{time_points[3]})'[v4];"
                f"[v4]drawbox=x=0:y=1910:w='iw*(t/{total_duration})':h=10:color=0xf43f5e@1:t=fill[vout]"
            )

            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"gradients=s={self.WIDTH}x{self.HEIGHT}:c0=0x0f172a:c1=0x1e1b4b:speed=0.015:d={total_duration}",
                "-i", scene_png_paths[0],
                "-i", scene_png_paths[1],
                "-i", scene_png_paths[2],
                "-i", scene_png_paths[3],
                "-i", audio_path,
                "-filter_complex", fc,
                "-map", "[vout]",
                "-map", "5:a",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", str(total_duration),
                "-movflags", "+faststart",
                final_video_path
            ]

            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                err_msg = proc.stderr.decode()[:350]
                return {"ok": False, "error": f"FFmpeg render error: {err_msg}"}

            if not os.path.exists(final_video_path) or os.path.getsize(final_video_path) < 1000:
                return {"ok": False, "error": "File video yang dihasilkan kosong atau gagal dibuat."}

            return {
                "ok": True,
                "video_path": final_video_path,
                "video_url": f"/static/videos/{video_filename}",
                "thumbnail_url": f"/static/thumbnails/{thumb_filename}",
                "filesize": os.path.getsize(final_video_path),
                "resolution": f"{self.WIDTH}x{self.HEIGHT} (9:16)",
                "duration": total_duration
            }
        finally:
            for p in scene_png_paths:
                if os.path.exists(p):
                    try:
                        os.unlink(p)
                    except Exception:
                        pass
