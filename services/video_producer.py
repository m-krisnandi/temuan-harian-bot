"""Mesin Produksi Video Vertikal 9:16 (1080x1920) Dinamis untuk TikTok Shop Affiliate & Reels.
Diadaptasi dari arsitektur Remotion / Cultiv Video Producer.
Menghasilkan video bergerak nyata (motion video):
1. Latar belakang dinamis bergerak (fluid moving ambient gradient background)
2. Dukungan ganda visual produk:
   - Jika tersedia Video Asli (Seller Video / Review MP4): Diputar langsung di dalam frame produk.
   - Jika hanya ada Foto Produk: Diterapkan Ken Burns Camera Motion (smooth zoom in/out + pan kamera dinamis).
3. Transisi multi-adegan (multi-scene cutscenes) dengan subtitle kinetik tersinkronisasi narasi suara.
4. Badge hook, masalah, rating, dan CTA interaktif berganti per adegan.
5. Garis durasi dinamis TikTok (progress bar) yang berjalan mulus di bagian paling bawah layar.
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
    FPS = 25

    # Area viewport media produk di dalam card (X1, Y1, X2, Y2)
    MEDIA_X = 105
    MEDIA_Y = 285
    MEDIA_W = 870
    MEDIA_H = 770

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

    def _download_or_resolve_video(self, video_url: str) -> Optional[str]:
        """Mengunduh video sumber dari URL atau mengembalikan path lokal jika sudah ada di server."""
        if not video_url:
            return None
        try:
            if video_url.startswith("http://") or video_url.startswith("https://"):
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                tmp_vid = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                with requests.get(video_url, headers=headers, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=16384):
                        tmp_vid.write(chunk)
                tmp_vid.close()
                return tmp_vid.name
            # Path relatif atau lokal
            if video_url.startswith("/"):
                # Cek path lokal relatif terhadap project
                local_p = os.path.join(os.path.dirname(__file__), "..", video_url.lstrip("/"))
                if os.path.exists(local_p):
                    return local_p
                if os.path.exists(video_url):
                    return video_url
            elif os.path.exists(video_url):
                return video_url
        except Exception as e:
            print(f"[VIDEO DOWNLOAD ERROR] Gagal memuat video sumber {video_url[:60]}: {e}")
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
        highlight_cta: bool = False,
        is_transparent_window: bool = True
    ) -> Image.Image:
        """Merender satu frame 1080x1920 layout kartu TikTok Affiliate.
        Jika is_transparent_window=True, area produk di tengah dibiarkan transparan agar
        video asli seller atau animasi Ken Burns motion di layer bawah terlihat mulus.
        """
        # Outer base transparan agar moving gradient terlihat di luar elemen kartu
        base_bg = (0, 0, 0, 0) if is_transparent_window else (15, 23, 42, 255)
        canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), base_bg)
        draw = ImageDraw.Draw(canvas)

        # 1. Background Blur Ambient (hanya jika thumbnail statis)
        if product_img and not is_transparent_window:
            try:
                bg_thumb = product_img.resize((self.WIDTH, self.HEIGHT), Image.Resampling.BILINEAR)
                bg_blur = bg_thumb.filter(ImageFilter.GaussianBlur(radius=35))
                dark_overlay = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (10, 15, 30, 200))
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

        # 3. Product Center Display Card Border
        card_box = [90, 270, 990, 1170]
        card_outline = (250, 204, 21, 220) if highlight_cta else (255, 255, 255, 75)
        # Gambar outline border kartu utama
        draw.rounded_rectangle(card_box, radius=32, outline=card_outline, width=4)

        # Jika thumbnail (non-transparan), tempelkan gambar produk ke tengah
        if not is_transparent_window and product_img:
            avail_w = 840
            avail_h = 750
            p_w, p_h = product_img.size
            ratio = min(avail_w / p_w, avail_h / p_h)
            new_w = int(p_w * ratio)
            new_h = int(p_h * ratio)
            resized_p = product_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            paste_x = self.MEDIA_X + (self.MEDIA_W - new_w) // 2
            paste_y = self.MEDIA_Y + (self.MEDIA_H - new_h) // 2
            canvas.paste(resized_p, (paste_x, paste_y), resized_p if resized_p.mode == "RGBA" else None)

        # 4. Info Bar Bawah Gambar (Harga & Rating)
        price_val = product.get("price", 0)
        rating_val = product.get("rating", 4.8)
        sales_val = product.get("sales", 0)

        info_box = [110, 1070, 970, 1150]
        draw.rounded_rectangle(info_box, radius=18, fill=(15, 23, 42, 245), outline=(250, 204, 21, 140), width=2)
        font_price = self._get_font(36, bold=True)
        font_meta = self._get_font(28, bold=False)

        price_str = f"Rp {price_val:,.0f}".replace(",", ".")
        rating_str = f"★ {rating_val:.1f}" + (f" | {sales_val:,} Terjual" if sales_val else "")

        draw.text((150, 1110), price_str, fill=(250, 204, 21), font=font_price, anchor="lm")
        draw.text((930, 1110), rating_str, fill=(226, 232, 240), font=font_meta, anchor="rm")

        # 5. Dynamic Subtitle Overlay Box (TikTok Safe Area: 1220 - 1440)
        subtitle_text = active_subtitle or script.get("hook") or product.get("product_name", "")
        if len(subtitle_text) > 90:
            subtitle_text = subtitle_text[:87] + "..."

        sub_box = [80, 1220, 1000, 1440]
        sub_border = (250, 204, 21, 230) if highlight_cta else (244, 63, 94, 200)
        draw.rounded_rectangle(sub_box, radius=24, fill=(0, 0, 0, 230), outline=sub_border, width=3)
        font_sub = self._get_font(38, bold=True)

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
        cta_color = (234, 179, 8, 255) if highlight_cta else (250, 204, 21, 245)
        cta_outline = (255, 255, 255, 200) if highlight_cta else None
        draw.rounded_rectangle(cta_box, radius=28, fill=cta_color, outline=cta_outline, width=3 if highlight_cta else 0)
        font_cta = self._get_font(38, bold=True)

        cta_text = "👉 KLIK KERANJANG KUNING SEKARANG" if highlight_cta else (script.get("overlay_cta") or "CEK KERANJANG KUNING SEKARANG")
        draw.text((self.WIDTH // 2, 1530), cta_text, fill=(15, 23, 42), font=font_cta, anchor="mm")

        # Watermark Temuan Harian
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
        """Merender video vertikal 9:16 dinamis multi-scene H.264 MP4 berdurasi pas dengan audio Gemini TTS.
        Mendukung video asli seller atau Ken Burns smooth motion jika hanya ada foto produk.
        """
        if not os.path.exists(audio_path):
            return {"ok": False, "error": f"File audio voiceover tidak ditemukan: {audio_path}"}

        item_id = str(product.get("item_id", "prod_video"))
        clean_name = "".join(c for c in product.get("product_name", "item") if c.isalnum() or c in ("-", "_")).rstrip()[:25]

        if not video_filename:
            video_filename = f"tiktok_{item_id}_{clean_name}.mp4"

        final_video_path = os.path.join(self.output_dir, video_filename)
        thumb_filename = f"thumb_{item_id}_{clean_name}.jpg"
        final_thumb_path = os.path.join(self.thumb_dir, thumb_filename)

        # 1. Deteksi durasi audio tepat
        total_duration = self.get_audio_duration(audio_path)
        if total_duration <= 2.0:
            total_duration = 15.0

        total_frames = int(math.ceil(total_duration * self.FPS))

        # 2. Periksa apakah produk memiliki Video Asli (Seller Video / Review MP4)
        raw_video_url = product.get("source_video_url") or product.get("video_url") or ""
        is_real_source_video = False
        if raw_video_url and not raw_video_url.startswith("/static/videos/") and "tiktok_" not in raw_video_url:
            is_real_source_video = True

        tmp_files_to_clean = []
        source_media_path = None

        if is_real_source_video:
            resolved_vid = self._download_or_resolve_video(raw_video_url)
            if resolved_vid and os.path.exists(resolved_vid):
                source_media_path = resolved_vid
                if resolved_vid.endswith(".tmp") or "tmp" in resolved_vid:
                    tmp_files_to_clean.append(resolved_vid)

        # Fallback ke Foto Produk jika video asli tidak ada atau gagal diunduh
        product_img = None
        if not source_media_path:
            img_url = product.get("image_url", "")
            product_img = self._download_image(img_url)
            if product_img:
                tmp_img = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                # Pad/fit image agar memiliki resolusi tinggi untuk Ken Burns
                p_rgb = product_img.convert("RGB")
                p_rgb.save(tmp_img.name, "JPEG", quality=95)
                tmp_img.close()
                source_media_path = tmp_img.name
                tmp_files_to_clean.append(tmp_img.name)

        if not source_media_path or not os.path.exists(source_media_path):
            return {"ok": False, "error": "Media gambar atau video produk tidak tersedia untuk dirender."}

        # 3. Susun 4 Scene Dinamis berdasarkan naskah narasi
        hook_text = script.get("hook") or product.get("product_name", "")
        opening_text = script.get("opening") or script.get("main_narration") or "Desain simpel dan praktis banget buat kebutuhan sehari-hari."
        body_text = script.get("main_narration") or script.get("supporting") or f"Sudah terbukti disukai dengan rating {product.get('rating', 4.8)}."
        cta_text = script.get("cta") or "Langsung amankan barang ini di keranjang kuning selagi promo!"

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
                "badge_bg": (244, 63, 94),
                "badge_fg": (255, 255, 255),
                "highlight_cta": False
            },
            {
                "subtitle": opening_text,
                "badge": "💡 SOLUSI PRAKTIS TERUJI",
                "badge_bg": (16, 185, 129),
                "badge_fg": (255, 255, 255),
                "highlight_cta": False
            },
            {
                "subtitle": body_text,
                "badge": f"⭐ RATING {product.get('rating', 4.8):.1f} • TERBUKTI DISUKAI",
                "badge_bg": (245, 158, 11),
                "badge_fg": (255, 255, 255),
                "highlight_cta": False
            },
            {
                "subtitle": cta_text,
                "badge": "🛒 CEK KERANJANG KUNING SEKARANG",
                "badge_bg": (234, 179, 8),
                "badge_fg": (15, 23, 42),
                "highlight_cta": True
            }
        ]

        # Titik waktu peralihan adegan
        t1 = round(total_duration * 0.25, 2)
        t2 = round(total_duration * 0.55, 2)
        t3 = round(total_duration * 0.80, 2)
        time_points = [0.0, t1, t2, t3, total_duration]

        # 4. Render 4 Frame PNG Overlay dengan Jendela Media Transparan
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
                    highlight_cta=sc["highlight_cta"],
                    is_transparent_window=True
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
                        is_transparent_window=False
                    )
                    thumb_frame.convert("RGB").save(final_thumb_path, "JPEG", quality=90)

                tmp_png = tempfile.NamedTemporaryFile(suffix=f"_sc{idx}.png", delete=False)
                frame.save(tmp_png.name, "PNG")
                tmp_png.close()
                scene_png_paths.append(tmp_png.name)
                tmp_files_to_clean.append(tmp_png.name)

            # 5. Susun Filter Complex FFmpeg
            # Input 0: Background moving gradient
            # Input 1: Source media (Video Asli atau Foto Produk)
            # Input 2..5: Multi-scene PNG overlays
            # Input 6: TTS Voiceover Audio
            if is_real_source_video:
                # Video asli di-scale & crop pas dengan viewport kartu (870x770)
                media_filter = f"[1:v]scale={self.MEDIA_W}:{self.MEDIA_H}:force_original_aspect_ratio=increase,crop={self.MEDIA_W}:{self.MEDIA_H},setsar=1[prod_stream];"
            else:
                # Foto produk diberi Ken Burns Camera Motion halus (smooth zoom in/out + pan)
                # Periode zoom: 125 frame (~5 detik), periode pan horizontal: 75 frame (~3 detik)
                media_filter = (
                    f"[1:v]zoompan=z='1.06+0.06*sin(2*PI*in/125)':"
                    f"x='(iw-iw/zoom)/2+25*sin(2*PI*in/75)':"
                    f"y='(ih-ih/zoom)/2':"
                    f"d={total_frames}:"
                    f"s={self.MEDIA_W}x{self.MEDIA_H}:fps={self.FPS},setsar=1[prod_stream];"
                )

            fc = (
                f"{media_filter}"
                f"[0:v][prod_stream]overlay={self.MEDIA_X}:{self.MEDIA_Y}[bg_prod];"
                f"[bg_prod][2:v]overlay=0:0:enable='between(t,{time_points[0]},{time_points[1]})'[v1];"
                f"[v1][3:v]overlay=0:0:enable='between(t,{time_points[1]},{time_points[2]})'[v2];"
                f"[v2][4:v]overlay=0:0:enable='between(t,{time_points[2]},{time_points[3]})'[v3];"
                f"[v3][5:v]overlay=0:0:enable='gte(t,{time_points[3]})'[v4];"
                f"[v4]drawbox=x=0:y=1910:w='iw*(t/{total_duration})':h=10:color=0xf43f5e@1:t=fill[vout]"
            )

            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"gradients=s={self.WIDTH}x{self.HEIGHT}:c0=0x0f172a:c1=0x1e1b4b:speed=0.015:d={total_duration}",
            ]

            if is_real_source_video:
                cmd.extend(["-stream_loop", "-1", "-i", source_media_path])
            else:
                cmd.extend(["-loop", "1", "-i", source_media_path])

            cmd.extend([
                "-i", scene_png_paths[0],
                "-i", scene_png_paths[1],
                "-i", scene_png_paths[2],
                "-i", scene_png_paths[3],
                "-i", audio_path,
                "-filter_complex", fc,
                "-map", "[vout]",
                "-map", "6:a",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", str(total_duration),
                "-movflags", "+faststart",
                final_video_path
            ])

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
                "duration": total_duration,
                "has_real_video": is_real_source_video
            }
        finally:
            for p in tmp_files_to_clean:
                if os.path.exists(p):
                    try:
                        os.unlink(p)
                    except Exception:
                        pass
