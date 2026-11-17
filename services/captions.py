"""Caption dan komentar produk multi-platform (Shopee & TikTok Shop).
Menerapkan Strategy Pattern & ICaptionGenerator (Open/Closed & Single Responsibility).
"""
import hashlib
from typing import Union, Dict, Any, Optional
from core.interfaces import ICaptionGenerator
from services.gemini_client import generate_educational_caption

_OPENERS = [
    "Temuan Hari Ini",
    "Rekomendasi Produk Pilihan",
    "Katalog Temuan Harian",
    "Produk Pilihan Hari Ini",
]


def rupiah(value) -> str:
    return "Rp" + f"{int(value):,}".replace(",", ".")


def short_sales(n) -> str:
    n = int(n)
    return f"{n // 1000}rb+" if n >= 1000 else f"{n}+"


def _short_name(name: str, limit: int = 90) -> str:
    name = " ".join(name.split())
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


class TemplateCaptionGenerator(ICaptionGenerator):
    """Generator caption berbasis template faktual terstruktur tanpa emoji."""

    def generate(self, item: Dict[str, Any]) -> str:
        idx = int(hashlib.md5(str(item.get("item_id", "0")).encode()).hexdigest(), 16) % len(_OPENERS)
        lines = [
            f"[{_OPENERS[idx]}]",
            "",
            _short_name(item.get("product_name", "Produk Pilihan")),
            "",
        ]
        if item.get("category"):
            lines.append(f"• Kategori: {item['category']}")
        if item.get("price"):
            lines.append(f"• Harga: Mulai dari {rupiah(item['price'])}")
        if item.get("discount_rate", 0) >= 1:
            lines.append(f"• Diskon: {int(item['discount_rate'])}%")
        if item.get("rating"):
            lines.append(f"• Rating Toko: {float(item['rating']):.1f} / 5.0")
        if item.get("sales"):
            lines.append(f"• Terjual: {short_sales(item['sales'])} produk")

        lines += [
            "",
            "Tautan toko resmi tersedia di komentar pertama.",
            "Harga dan ketersediaan dapat berubah sewaktu-waktu sesuai promo toko resmi."
        ]
        return "\n".join(lines)


class GeminiCaptionGenerator(ICaptionGenerator):
    """Generator caption edukatif berbasis Google Gemini AI (3.8 Flash)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model

    def generate(self, item: Dict[str, Any]) -> str:
        caption = generate_educational_caption(item, api_key=self.api_key, model=self.model)
        if not caption:
            raise RuntimeError("Gemini AI gagal menghasilkan caption")
        return caption


class CompositeCaptionGenerator(ICaptionGenerator):
    """Komposit generator caption: mencoba AI terlebih dahulu dengan fallback ke template."""

    def __init__(self, primary: ICaptionGenerator, fallback: ICaptionGenerator):
        self.primary = primary
        self.fallback = fallback

    def generate(self, item: Dict[str, Any]) -> str:
        try:
            return self.primary.generate(item)
        except Exception:
            return self.fallback.generate(item)


def build_caption(item: dict, use_ai: bool = True, gemini_api_key: Optional[str] = None) -> str:
    """Fungsi pembantu kompatibilitas mundur (backward-compatibility helper)."""
    template_gen = TemplateCaptionGenerator()
    if use_ai:
        gemini_gen = GeminiCaptionGenerator(api_key=gemini_api_key)
        composite = CompositeCaptionGenerator(primary=gemini_gen, fallback=template_gen)
        return composite.generate(item)
    return template_gen.generate(item)


def build_comment(link_or_item: Union[str, Dict[str, Any]]) -> str:
    """Format komentar referensi minimalis & bersih tanpa jargon promosi."""
    if isinstance(link_or_item, dict):
        shopee = link_or_item.get("affiliate_link", "")
        tiktok = link_or_item.get("tiktok_link", "")

        if shopee and tiktok:
            return f"Tautan referensi:\nShopee: {shopee}\nTikTok: {tiktok}"
        elif tiktok and not shopee:
            return f"Tautan referensi: {tiktok}"
        elif shopee:
            return f"Tautan referensi: {shopee}"
        return ""
    return f"Tautan referensi: {link_or_item}"
