"""Shopee Affiliate CSV Parser & Bulk Importer untuk Temuan Harian.
Memproses:
1. File CSV ekspor resmi Shopee Affiliate (LinkProdukSekaligus...csv).
2. Input single link atau daftar link banyak (multi-line).
3. Mengambil cover resmi asli penjual (Real Seller Media via WhatsApp scraper).
4. Menghasilkan caption edukasi renyah via Gemini AI.
5. Menjalankan Smart Market-Driven Scheduler otomatis.
"""
import csv
import io
import re
from typing import List, Dict, Any, Optional
from services.shopee_scraper import ShopeePublicScraper, detect_category
from services.gemini_client import generate_educational_caption
from services.captions import build_caption
from services.smart_scheduler import SmartScheduler, MarketRanker


def parse_indonesian_number(val: Any) -> float:
    """Mengonversi format angka khas Indonesia ('278,0RB', '10RB+', 'Rp44.480', '16,5%') ke float."""
    if not val:
        return 0.0
    s = str(val).strip().replace("Rp", "").replace(" ", "")

    # Cek satuan 'RB' atau 'rb' (Ribu)
    is_ribu = False
    if "rb" in s.lower():
        is_ribu = True
        s = re.sub(r"[rR][bB]\+?", "", s)

    # Cek persen '%'
    s = s.replace("%", "")

    # Format desimal Indonesia: '278,0' -> 278.0, '44.480' -> 44480
    if "," in s and "." in s:
        # Contoh 1.250,50
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # Contoh 278,0 atau 16,5
        s = s.replace(",", ".")
    elif "." in s and not is_ribu:
        # Contoh 44.480 (titik sebagai ribuan)
        parts = s.split(".")
        if len(parts[-1]) == 3:  # Kemungkinan besar pemisah ribuan
            s = s.replace(".", "")

    try:
        num = float(s)
        if is_ribu:
            num *= 1000.0
        return round(num, 2)
    except ValueError:
        # Ekstrak digit saja jika gagal
        digits = re.findall(r"\d+", str(val))
        if digits:
            base = float("".join(digits))
            return base * 1000.0 if is_ribu else base
        return 0.0


class ShopeeBulkImporter:
    """Mengorkestrasi proses impor massal dari CSV atau daftar link Shopee."""

    def __init__(self, scraper: Optional[ShopeePublicScraper] = None):
        self.scraper = scraper or ShopeePublicScraper()

    def parse_csv(self, csv_content: str) -> List[Dict[str, Any]]:
        """Membaca data CSV dari string / file upload."""
        items = []
        reader = csv.DictReader(io.StringIO(csv_content))

        for row in reader:
            # Cari kolom yang sesuai (toleran terhadap variasi penamaan header Shopee)
            item_id = row.get("ID Produk") or row.get("item_id") or ""
            product_name = row.get("Nama Produk") or row.get("product_name") or ""
            price_raw = row.get("Harga") or row.get("price") or 0
            sales_raw = row.get("Penjualan") or row.get("sales") or 0
            shop_name = row.get("Nama Toko") or row.get("shop_name") or ""
            comm_rate_raw = row.get("Komisi hingga") or row.get("commission_rate") or 0
            comm_amt_raw = row.get("Komisi") or row.get("commission_amount") or 0
            product_url = row.get("Link Produk") or row.get("product_url") or ""
            affiliate_link = row.get("Link Komisi Ekstra") or row.get("affiliate_link") or product_url

            if not product_name and not product_url and not affiliate_link:
                continue

            price = parse_indonesian_number(price_raw)
            sales = int(parse_indonesian_number(sales_raw))
            comm_rate = parse_indonesian_number(comm_rate_raw)
            comm_amt = parse_indonesian_number(comm_amt_raw)
            category = detect_category(product_name)

            items.append({
                "item_id": str(item_id).strip(),
                "product_name": product_name.strip(),
                "price": price,
                "sales": sales,
                "shop_name": shop_name.strip(),
                "commission_rate": comm_rate,
                "commission_amount": comm_amt,
                "product_url": product_url.strip(),
                "affiliate_link": affiliate_link.strip(),
                "category": category,
                "platform": "SHOPEE",
                "media_type": "IMAGE",
                "image_url": "",
                "video_url": "",
                "caption": ""
            })

        return items

    def process_and_enrich(
        self,
        raw_items: List[Dict[str, Any]],
        use_gemini: bool = True,
        gemini_api_key: Optional[str] = None,
        progress_callback=None
    ) -> List[Dict[str, Any]]:
        """Mengambil media asli seller dan menyusun caption edukasi untuk setiap produk."""
        enriched = []
        total = len(raw_items)

        for idx, it in enumerate(raw_items):
            url_to_scrape = it.get("affiliate_link") or it.get("product_url")
            # 1. Scrape real seller cover & video
            if url_to_scrape and (not it.get("image_url") or not it.get("product_name")):
                try:
                    scraped = self.scraper.scrape_preview(url_to_scrape)
                    if not it.get("image_url"):
                        it["image_url"] = scraped.get("image_url", "")
                    if not it.get("video_url") and scraped.get("video_url"):
                        it["video_url"] = scraped.get("video_url", "")
                        it["media_type"] = "VIDEO"
                    if not it.get("product_name") or it.get("product_name") == "Produk Shopee Pilihan":
                        it["product_name"] = scraped.get("product_name", it["product_name"])
                    if not it.get("price") and scraped.get("price"):
                        it["price"] = scraped.get("price", 0)
                    if it.get("category") == "Rumah Tangga & Dekorasi" and scraped.get("category"):
                        it["category"] = scraped.get("category")
                    if not it.get("item_id"):
                        it["item_id"] = scraped.get("item_id")
                except Exception:
                    pass

            # Pastikan item_id terisi
            if not it.get("item_id"):
                import uuid
                it["item_id"] = f"shp_{uuid.uuid4().hex[:10]}"

            # 2. Generate Caption Edukatif & Natural via AI
            if not it.get("caption"):
                caption = None
                if use_gemini:
                    try:
                        caption = generate_educational_caption(it, api_key=gemini_api_key)
                    except Exception:
                        caption = None
                if not caption:
                    caption = build_caption(it, use_ai=False)
                it["caption"] = caption

            # 3. Hitung Skor Pasar
            it["market_score"] = MarketRanker.calculate_score(it)
            enriched.append(it)

            if progress_callback:
                progress_callback(idx + 1, total, it["product_name"])

        # 4. Susun jadwal waktu emas otomatis (Smart Scheduling)
        scheduled_items = SmartScheduler.schedule_batch(enriched)
        return scheduled_items
